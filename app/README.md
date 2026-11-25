# Aplicação do LinkPulse

API em Python com FastAPI que cadastra clientes e campanhas, cria links curtos, redireciona, registra cada clique e consulta o histórico de cliques ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md)), na stack do [ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md). Esta pasta tem os passos 2 a 5 do plano da spec: o cadastro de cliente, campanha e criação de link (RM-36), o redirecionamento, o contador e a gravação assíncrona do clique (RM-37), as consultas de analytics (RM-38) e a tela (RM-39).

| Arquivo | O que tem |
| --- | --- |
| [main.py](main.py) | Monta a aplicação: abre as conexões e registra as rotas |
| [router.py](router.py) | As rotas, que chamam o service ou o analytics e devolvem 200, 201, 302, 404, 410, 422 ou 503, e a página da tela |
| [service.py](service.py) | O cadastro e a listagem de clientes, campanhas e links, o sorteio do `short_code` e a leitura do link no redirecionamento |
| [cliques.py](cliques.py) | A gravação assíncrona do clique no Cassandra, o contador de falhas e a classificação do dispositivo |
| [analytics.py](analytics.py) | As quatro consultas de analytics: a leitura das partições no Cassandra e o agrupamento por dia, por canal e por dispositivo |
| [models.py](models.py) | Os formatos dos pedidos, com a validação da URL, do `expira_em` e da janela das consultas |
| [static/](static/) | A tela: [index.html](static/index.html), [painel.css](static/painel.css), [painel.js](static/painel.js), [dados.js](static/dados.js), com a busca e a conferência dos dados sem DOM, e o Chart.js em [vendor/](static/vendor/chart.js-4.6.1/) |
| [tests/](tests/) | Os testes dos critérios CA-1 a CA-10, CA-12, CA-13 e CA-15 a CA-17 e das respostas de erro |

## Como rodar

A aplicação roda no computador, fora do Docker, e usa os bancos do [ambiente de desenvolvimento](../infra/README.md#como-usar).

1. Suba os bancos com os volumes de desenvolvimento: `docker compose up -d --wait`.
2. Crie o ambiente Python uma vez, na raiz do repositório:

   ```sh
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-testes.txt   # no Linux e no macOS: .venv/bin/python
   ```

3. Suba a API: `.venv/Scripts/python -m uvicorn app.main:app --port 8000`.

A tela fica em `http://127.0.0.1:8000/`, e a documentação interativa das rotas, em `http://127.0.0.1:8000/docs`. A API conecta ao Cassandra ao subir, então ele precisa estar no ar nesse momento. Depois, uma queda do Cassandra não interrompe os redirecionamentos, e o driver reconecta sozinho quando ele volta. Subir a API durante uma queda fica fora do ambiente controlado da demonstração, em que os bancos sobem com `--wait` antes da API (Q-44).

Por padrão, a aplicação usa estes bancos, que as variáveis de ambiente mudam:

| Banco | Padrão | Variáveis |
| --- | --- | --- |
| Redis master | `127.0.0.1:6379` | `REDIS_MASTER_HOST`, `REDIS_MASTER_PORT` |
| Redis réplica | `127.0.0.1:6380` | `REDIS_REPLICA_HOST`, `REDIS_REPLICA_PORT` |
| MongoDB | `mongodb://127.0.0.1:27017`, banco `linkpulse` | `MONGO_URL`, `MONGO_DB` |
| Cassandra | `127.0.0.1:9042`, keyspace `linkpulse` | `CASSANDRA_HOST`, `CASSANDRA_PORT`, `CASSANDRA_KEYSPACE` |

O padrão é `127.0.0.1`, e não `localhost`, porque as portas do Compose só escutam em IPv4, e no Windows cada conexão a `localhost` espera cerca de 2 s pela tentativa em IPv6.

**No Windows**, o `requirements.txt` instala também o `pyasyncore`. O `cassandra-driver` não tem a extensão libev compilada para Windows, e o módulo `asyncore`, a outra opção do driver, saiu do Python 3.12; o `pyasyncore` traz esse módulo de volta. No Linux, inclusive nos contêineres, o driver usa a libev e o pacote não é instalado (Q-43).

## Rotas

| Rota | Corpo | Resposta |
| --- | --- | --- |
| `POST /clientes` | `{nome}` | `201 {cliente_id}` |
| `GET /clientes` | — | `200 [{cliente_id, nome}]`, em ordem de nome |
| `POST /campanhas` | `{cliente_id, nome, descricao?, tags?}` | `201 {campanha_id}` |
| `GET /campanhas?cliente_id` | — | `200 [{campanha_id, nome, descricao, tags, links}]`, em ordem de nome |
| `POST /links` | `{url, cliente_id, canal?, expira_em?, campanha_id?}` | `201 {short_code}` |
| `GET /links?cliente_id` | — | `200 [{short_code, url, canal, criado_em, expira_em, contador}]`, do mais novo ao mais antigo |
| `GET /r/{short_code}` | — | `302` com `Location` igual à `url` gravada, com o domínio em IDNA se tiver acento |
| `GET /metricas` | — | `200 {falhas_gravacao_clique}` |
| `GET /analytics/por-dia?short_code&inicio&fim` | — | `200 {short_code, dias: [{dia, cliques}]}` |
| `GET /analytics/por-canal?cliente_id&inicio&fim` | — | `200 {cliente_id, canais: [{short_code, canal, cliques}]}` |
| `GET /analytics/por-dispositivo?short_code&inicio&fim` | — | `200 {short_code, dispositivos: [{dispositivo, cliques}]}` |
| `GET /analytics/total?short_code&inicio&fim` | — | `200 {short_code, cliques}` |
| `GET /` | — | `200`, a página da tela |

Exemplo:

```sh
curl -X POST http://127.0.0.1:8000/links -H "content-type: application/json" \
  -d '{"url": "https://exemplo.com.br/natal", "cliente_id": "c1", "canal": "instagram"}'
curl -i http://127.0.0.1:8000/r/{short_code}
curl "http://127.0.0.1:8000/analytics/por-dia?short_code={short_code}&inicio=2026-11-18T00:00:00-03:00&fim=2026-11-24T23:59:59.999-03:00"
```

### Onde cada dado fica

- **Cliente:** Hash `cliente:{cliente_id}` com o nome, e o `cliente_id` no Set `clientes`. A listagem lê só esse Set, e os clientes da base do benchmark ficam fora dele ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#dados-novos-da-aplicação)).
- **Campanha:** um documento na coleção `campanhas` do MongoDB, com `cliente_id`, `nome`, `descricao`, `tags` e `links`, que começa vazia. O `campanha_id` é o `_id` do documento.
- **Link:** Hash `link:{short_code}` com `url`, `cliente_id`, `criado_em` e, se informados, `canal` e `expira_em`. As datas ficam em UTC, no formato `2026-12-25T23:59:59.000Z`, o mesmo da base do benchmark. O código entra no Set `links:cliente:{cliente_id}` e, com `campanha_id`, no fim da lista `links` da campanha.
- **Contador de cliques:** a chave `contador:{short_code}` no Redis master, que só existe depois do primeiro clique. `GET /links` o devolve como `contador`, com `0` antes do primeiro clique (Q-54).
- **Clique:** uma linha em `cliques_por_link` no Cassandra, com `short_code`, `clicado_em` (em milissegundos, UTC), `clique_id` (um `timeuuid` do mesmo instante), `dispositivo` e `referrer`, este vindo do cabeçalho `Referer`. O `pais` fica vazio. A aplicação só faz `INSERT` nessa tabela.
- **Falhas de gravação do clique:** um contador na memória da aplicação, que volta a zero quando ela reinicia (Q-42).

### Como o `short_code` é gerado

Sete caracteres em Base62, cada um sorteado com o módulo `secrets` do Python, sem contador nem relógio (RN-01). Um script Lua grava o Hash e inclui o código no Set do cliente numa só operação, e só se a chave `link:{short_code}` ainda não existir. Em colisão, a aplicação sorteia outro código, até 5 vezes.

### O caminho de um clique

1. A aplicação lê `link:{short_code}` na réplica do Redis. Se o link não está lá, por ainda não ter sido copiado, ou se a réplica não responde, lê do master. As conexões com o Redis não fazem novas tentativas: na réplica, a leitura que falha vai direto ao master (Q-31); no master, um `INCR` repetido depois de uma resposta perdida somaria o mesmo clique duas vezes. Valem os tempos limite padrão do `redis-py`, de 5 s para conectar e 5 s para cada resposta.
2. Sem o link no master, responde `404`. Com `expira_em` já passado, responde `410` com uma página HTML de link expirado. Nos dois casos, nada é contado nem gravado (RN-03).
3. Caso contrário, responde `302`. Um domínio com acento vai no `Location` como o validador do cadastro o aceitou, em IDNA: `https://café.example/oferta` sai como `https://xn--caf-dma.example/oferta`, e `https://faß.example` como `https://xn--fa-hia.example`. Nesse caso, a URL sai na forma normalizada pelo validador, que é equivalente à gravada; ele tira, por exemplo, a porta padrão (`:443`). URLs com domínio sem acento saem exatamente como foram gravadas. Só depois que a resposta sai, a aplicação envia o clique ao Cassandra, sem esperar a confirmação, e executa `INCR contador:{short_code}` no master.
4. A gravação do clique tem tempo limite de 2 s (Q-41). Se ela falhar ou passar desse tempo, o clique é descartado, sem nova tentativa: a falha vai para o log, com o `short_code` e o erro, e soma 1 em `falhas_gravacao_clique`, em `GET /metricas` (RN-07). O contador do Redis soma mesmo assim. Se o `INCR` falhar, a falha vai para o log e a resposta já enviada não muda.

O dispositivo sai do cabeçalho `User-Agent` (Q-37): `tablet` para iPad, tablets Android (Android sem `Mobile`) e User-Agent com `Tablet`; `mobile` para iPhone, celulares Android e demais User-Agent com `Mobi`; `desktop` para Windows, macOS, Linux e ChromeOS. Fica `outro` o User-Agent ausente, o de robôs e pré-visualizações de redes sociais (`bot`, `crawl`, `spider`, `facebookexternalhit`, `WhatsApp` e outros), o de `curl` e `wget` e o que não se encaixa em nenhuma regra.

### As consultas de analytics

As quatro consultas contam os cliques de `cliques_por_link` no intervalo fechado `[inicio, fim]`, os dois em ISO 8601 com fuso, como o `expira_em` (Q-45). Na query string, o `+` de um fuso como `+00:00` vira espaço; use `Z`, `-03:00` ou `%2B00:00`. A fração do segundo vale com qualquer número de casas, separada por ponto ou vírgula: a comparação entre `inicio` e `fim` usa todas elas. O Cassandra guarda milissegundos, então um limite com fração menor que o milissegundo vai para o milissegundo seguinte, no início, ou para o anterior, no fim: `12:00:00.000500Z` ou `12:00:00.000000001Z` a `12:00:00.001Z` não inclui um clique de `12:00:00.000Z`.

- **Por dia:** lê os instantes dos cliques do link e conta por dia do horário de Brasília (`America/Sao_Paulo`), com um item para cada dia que o intervalo toca e `0` nos dias sem clique (Q-46, Q-47). Um clique às 22:30 de 20/11 em Brasília, gravado como 21/11 01:30 UTC, conta em 20/11.
- **Por canal:** lê no master do Redis os links do Set `links:cliente:{cliente_id}` e o `canal` de cada um, e conta os cliques de cada link no Cassandra, uma consulta por partição, todas em paralelo. Os links vêm em ordem decrescente de cliques e, no empate, de `short_code`; o link sem canal vem com `canal` nulo (Q-46).
- **Por dispositivo:** lê a coluna `dispositivo` dos cliques do link e conta por categoria. A resposta traz sempre `mobile`, `desktop`, `tablet` e `outro`, nessa ordem, com `0` nas que não têm clique (Q-49).
- **Total:** um `SELECT COUNT(*)` na partição do link.

Cada consulta CQL informa `short_code`, a partition key, e lê um trecho contínuo da partição, sem `ALLOW FILTERING` (RNF-06). As consultas por link conferem antes, no master do Redis, que o link existe. O master, e não a réplica, porque um link recém-criado pode ainda não ter chegado a ela; as consultas de analytics são poucas e não disputam com o redirecionamento.

### Erros

Respostas decididas no Q-40, no Q-48 e no RN-03 ([QUESTOES](../docs/requisitos/QUESTOES.md#respondidas)):

| Situação | Resposta | O que é gravado |
| --- | --- | --- |
| Campo obrigatório ausente ou vazio, URL que não começa com `http://` ou `https://` seguido de um host válido, URL com mais de 2.083 caracteres (limite do `HttpUrl` do Pydantic), `expira_em` que não é data ISO 8601 com hífens e fuso (`2026-12-25T23:59:59Z`) | `422` | Nada |
| `campanha_id` que não existe ou de uma campanha de outro cliente (Q-55) | `422` | Nada |
| Em `POST /links`, falha de gravação no Redis ou 5 colisões seguidas | `503`, sem `short_code` | Nada no MongoDB |
| Em `GET /r/{short_code}`, link que não existe | `404` | Nada |
| Em `GET /r/{short_code}`, link com `expira_em` no passado | `410`, com a página de link expirado | Nada |
| Nas consultas, `short_code`, `cliente_id`, `inicio` ou `fim` ausente ou vazio, data sem fuso ou fora de ISO 8601, ou `inicio` depois de `fim` (Q-48) | `422` | — |
| Em `por-dia`, `por-dispositivo` e `total`, link que não existe | `404` | — |
| Em `GET /links` e `GET /campanhas`, sem `cliente_id` ou com ele vazio | `422` | — |
| Em `por-canal`, cliente sem links | `200` com `canais` vazia | — |

A aplicação não confere se o `cliente_id` foi cadastrado ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md#fora-de-escopo)). A campanha do link precisa ser do mesmo cliente (Q-55).

## A tela

A página em `GET /` é HTML, CSS e JavaScript puros, sem framework e sem etapa de build ([ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md)). Na lateral, escolhe-se ou cadastra-se o cliente, cadastram-se campanhas e criam-se links; a lista mostra os links do cliente, do mais novo ao mais antigo. Para o link escolhido, o painel mostra:

- o total de cliques dos últimos 7 dias, de `GET /analytics/total`, e, ao lado, os cliques desde a criação, do contador do Redis, que pode ser maior que o histórico (Q-51);
- os cliques por dia, com hoje em destaque, e por dispositivo;
- os cliques de cada link do cliente, com a participação no total do cliente;
- a campanha, com a descrição e as tags, quando o link faz parte de uma: a página a acha na lista de `GET /campanhas` cuja lista `links` contém o link (Q-50).

Os "últimos 7 dias" terminam no fechamento, 5 s antes do momento da leitura, e são os 7 dias de Brasília até ele, calculados pelo navegador com o fuso `America/Sao_Paulo`, e não pelo fuso do computador: `inicio` à 00:00 de 6 dias antes do dia do fechamento e `fim` no próprio fechamento, em UTC (Q-53, Q-57). A página refaz as consultas e relê as campanhas a cada 5 s, sem recarregar, e mostra a hora da última atualização. Um clique novo aparece em até cerca de 10 s, os 5 s da margem mais os 5 s do intervalo, dentro dos 60 s do RNF-03 (Q-52).

As quatro consultas leem o Cassandra em momentos diferentes. A margem de 5 s, maior que os 2 s de tempo limite da gravação (Q-41), faz todas verem o mesmo conjunto: até o fechamento, todo clique já foi gravado ou descartado (Q-57). Como proteção para um relógio do navegador adiantado, a página só publica um conjunto em que o total, a soma das barras, a soma dos dispositivos e os cliques do link na comparação por canal são iguais. Se não forem, refaz as consultas na hora, com até 3 leituras no total por ciclo; se ainda não baterem, avisa que os cliques mudaram durante a leitura e mantém o último conjunto coerente até o ciclo seguinte (Q-56). A busca, essa conferência e o cálculo da janela ficam em [dados.js](static/dados.js), sem DOM, para serem testados fora do navegador. Se uma atualização falha, um aviso aparece, os últimos dados continuam na tela e a página tenta de novo no ciclo seguinte.

Os gráficos usam o Chart.js 4.6.1, servido pela aplicação em `/static/vendor/chart.js-4.6.1/`, com a licença MIT ao lado, para a tela funcionar sem internet. O arquivo é o `dist/chart.umd.min.js` do pacote `chart.js@4.6.1` do npm, com SHA-256 `87364cc2b2a76a6684929e7d6b80b18a897794db38400caff1fcf1791c6925d2`. Para trocar de versão, baixe o pacote, confira a integridade publicada no npm e mude a pasta e a referência em [index.html](static/index.html).

## Como testar

Com os bancos de desenvolvimento no ar, o ambiente Python criado e o Node 18 ou mais novo no `PATH`, usado só pelos testes da tela (Q-56):

```sh
.venv/Scripts/python -m pytest app
```

Os testes usam o banco 15 do Redis, o banco `linkpulse_testes` do MongoDB e o keyspace `linkpulse_testes` do Cassandra. O Redis e o MongoDB esvaziam antes e depois de cada teste. O keyspace é criado na primeira execução, com o mesmo [esquema](../infra/cassandra/esquema.cql) da aplicação, e cada teste apaga no fim os cliques dos links que criou. Os clientes, links e cliques da demonstração, no banco 0, no banco `linkpulse` e no keyspace `linkpulse`, não mudam. O teste da modelagem só lê o esquema do keyspace `linkpulse` e o papel de cada Redis. Rode os testes com os volumes de desenvolvimento, e não com os do benchmark. A suíte leva cerca de 30 s.

| Arquivo | O que confere |
| --- | --- |
| [test_clientes.py](tests/test_clientes.py) | CA-1: o cliente cadastrado aparece na listagem, e um cliente gravado como a carga do benchmark grava, fora do Set `clientes`, não aparece; sem `nome`, `422` |
| [test_campanhas.py](tests/test_campanhas.py) | Os campos do documento da campanha, com `links` vazia; sem `cliente_id` ou `nome`, `422`. A listagem traz só as campanhas do cliente, em ordem de nome e com os links; sem `cliente_id`, `422` |
| [test_links.py](tests/test_links.py) | CA-2: os campos do Hash do link e o Set do cliente. CA-3 e Q-40: pedidos rejeitados com `422`, sem nada gravado no Redis nem na campanha. CA-5: a colisão preserva o link existente e o novo link recebe outro código. CA-6: o código entra na lista `links` da campanha. Q-55: `campanha_id` de outro cliente responde `422` sem gravar nada. RN-08: com a réplica, que recusa escritas, e com o Redis fora do ar, a resposta é `503` sem `short_code` e a campanha não muda. A listagem traz só os links do cliente, do mais novo ao mais antigo, com o contador e os campos ausentes nulos; sem `cliente_id`, `422` |
| [test_short_code.py](tests/test_short_code.py) | CA-4: 10.000 códigos com 7 caracteres em Base62, sem dois seguidos que difiram só no último caractere |
| [test_redirecionamento.py](tests/test_redirecionamento.py) | CA-7: link sem `expira_em` responde `302` com a `url` gravada, com o relógio em 2100. CA-8: link expirado responde `410`, sem contador e sem linha no Cassandra. CA-9: código inexistente responde `404`. CA-10: link fora da réplica, num banco aonde a cópia não chega, e réplica fora do ar respondem `302`, lidos do master. CA-12: o clique vira uma linha com `short_code`, `clicado_em`, `clique_id`, dispositivo e referrer, e nenhum arquivo da aplicação tem `UPDATE`. CA-13: 50 acessos concorrentes somam exatamente 50 no contador e gravam 50 linhas, e um `INCR` cuja resposta se perde soma uma vez só. Um domínio com acento sai em IDNA no `Location`. RN-07: com o Cassandra simulado fora do ar, a resposta continua `302`, a falha vai para o log e `GET /metricas` mostra 1. A classificação do dispositivo para 11 User-Agent |
| [test_analytics.py](tests/test_analytics.py) | CA-15: com cliques gravados em instantes conhecidos, dentro e fora da janela de 20/11 a 22/11/2026 em Brasília, as consultas por dia, por canal e total dão as contagens esperadas: o clique no próprio início e no próprio fim conta, o de 1 ms antes ou depois não; um clique às 22:30 em Brasília conta no dia de Brasília, e não no de UTC; dois cliques no mesmo milissegundo contam dois; um limite com fração menor que o milissegundo, até além do microssegundo, não inclui um clique fora do intervalo, e um `inicio` depois do `fim` só no nanossegundo responde `422`, nas quatro consultas; dias sem clique vêm com `0`; o canal compara só os links do cliente, com empate por `short_code` e o link sem canal com `canal` nulo; a consulta por dispositivo traz as quatro categorias, com `0` na que não tem clique, e não conta os cliques fora da janela (Q-49). Os cliques de três redirecionamentos, de dois iPhones e um Windows, aparecem nas quatro consultas. Os comandos CQL executados informam `short_code` e não usam `ALLOW FILTERING`. Q-48: pedidos inválidos com `422`, link inexistente com `404`, link sem cliques com zeros e cliente sem links com lista vazia |
| [test_tela.py](tests/test_tela.py) | CA-17: a janela que a tela envia fecha 5 s antes de agora, inclusive nos primeiros segundos do dia; nela, o total, as 7 barras por dia, os dispositivos e os canais batem entre si e com cliques gravados nos limites da janela, e o contador vem da listagem. Dois redirecionamentos aparecem nos dados da tela, com a janela recalculada a cada leitura, em menos de 60 s, já somado o intervalo de atualização da página. A página sai em `GET /`, carrega o `dados.js` antes do `painel.js` e referencia só arquivos de `/static/`, todos servidos, com o Chart.js 4.6.1; nenhum arquivo da tela aponta para a internet; a margem é maior que os 2 s da gravação, e margem mais intervalo fica abaixo de 60 s |
| [test_dados_da_tela.py](tests/test_dados_da_tela.py) | Q-56 e Q-57: roda o [dados.js](static/dados.js) no Node, pelo [dados_da_tela.mjs](tests/dados_da_tela.mjs), com respostas controladas ou num relógio simulado. A janela da página é a mesma dos testes de dados, inclusive às 22:30 de Brasília; o conjunto coerente sai na primeira leitura; um clique entre a leitura do total e as outras faz a página refazer as consultas e publicar o conjunto coerente; sem coerência em 3 leituras, nada é publicado. Com 500 cliques por minuto, leituras a 130 ms uma da outra e a gravação no tempo limite, todo ciclo publica, e um clique chega à tela publicada em menos de 60 s. O contexto relê as campanhas a cada ciclo, e um link que entrou numa campanha por outra aba aparece com ela |
| [test_modelagem.py](tests/test_modelagem.py) | CA-16: no keyspace `linkpulse`, `short_code` é a única partition key, a ordem é `clicado_em DESC, clique_id DESC` e há fator de replicação; nenhum comando CQL da aplicação usa `ALLOW FILTERING`, e os que leem informam `short_code`; o Redis tem um master com réplica conectada e uma réplica |

O teste da réplica fora do ar não é o CA-11: ele usa uma porta sem servidor, e não a réplica do Compose derrubada. O CA-11 e o CA-14, com a réplica e o Cassandra de fato parados, entram nos testes de aceitação (RM-40).
