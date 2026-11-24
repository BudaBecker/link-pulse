# Aplicação do LinkPulse

API em Python com FastAPI que cadastra clientes e campanhas, cria links curtos, redireciona e registra cada clique ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md)), na stack do [ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md). Esta pasta tem os passos 2 e 3 do plano da spec: o cadastro de cliente, campanha e criação de link (RM-36) e o redirecionamento, o contador e a gravação assíncrona do clique (RM-37). As consultas de analytics e a tela entram nas tarefas seguintes (RM-38 e RM-39).

| Arquivo | O que tem |
| --- | --- |
| [main.py](main.py) | Monta a aplicação: abre as conexões e registra as rotas |
| [router.py](router.py) | As rotas, que chamam o service e devolvem 201, 302, 404, 410, 422 ou 503 |
| [service.py](service.py) | O cadastro de clientes e campanhas, a criação de links, o sorteio do `short_code` e a leitura do link no redirecionamento |
| [cliques.py](cliques.py) | A gravação assíncrona do clique no Cassandra, o contador de falhas e a classificação do dispositivo |
| [models.py](models.py) | Os formatos dos pedidos, com a validação da URL e do `expira_em` |
| [tests/](tests/) | Os testes dos critérios CA-1 a CA-10, CA-12 e CA-13 e das respostas de erro |

## Como rodar

A aplicação roda no computador, fora do Docker, e usa os bancos do [ambiente de desenvolvimento](../infra/README.md#como-usar).

1. Suba os bancos com os volumes de desenvolvimento: `docker compose up -d --wait`.
2. Crie o ambiente Python uma vez, na raiz do repositório:

   ```sh
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-testes.txt   # no Linux e no macOS: .venv/bin/python
   ```

3. Suba a API: `.venv/Scripts/python -m uvicorn app.main:app --port 8000`.

A documentação interativa das rotas fica em `http://127.0.0.1:8000/docs`. A API conecta ao Cassandra ao subir, então ele precisa estar no ar nesse momento; depois, uma queda do Cassandra não interrompe os redirecionamentos.

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
| `POST /links` | `{url, cliente_id, canal?, expira_em?, campanha_id?}` | `201 {short_code}` |
| `GET /r/{short_code}` | — | `302` com `Location` igual à `url` gravada |
| `GET /metricas` | — | `200 {falhas_gravacao_clique}` |

Exemplo:

```sh
curl -X POST http://127.0.0.1:8000/links -H "content-type: application/json" \
  -d '{"url": "https://exemplo.com.br/natal", "cliente_id": "c1", "canal": "instagram"}'
curl -i http://127.0.0.1:8000/r/{short_code}
```

### Onde cada dado fica

- **Cliente:** Hash `cliente:{cliente_id}` com o nome, e o `cliente_id` no Set `clientes`. A listagem lê só esse Set, e os clientes da base do benchmark ficam fora dele ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#dados-novos-da-aplicação)).
- **Campanha:** um documento na coleção `campanhas` do MongoDB, com `cliente_id`, `nome`, `descricao`, `tags` e `links`, que começa vazia. O `campanha_id` é o `_id` do documento.
- **Link:** Hash `link:{short_code}` com `url`, `cliente_id`, `criado_em` e, se informados, `canal` e `expira_em`. As datas ficam em UTC, no formato `2026-12-25T23:59:59.000Z`, o mesmo da base do benchmark. O código entra no Set `links:cliente:{cliente_id}` e, com `campanha_id`, no fim da lista `links` da campanha.
- **Contador de cliques:** a chave `contador:{short_code}` no Redis master, que só existe depois do primeiro clique.
- **Clique:** uma linha em `cliques_por_link` no Cassandra, com `short_code`, `clicado_em` (em milissegundos, UTC), `clique_id` (um `timeuuid` do mesmo instante), `dispositivo` e `referrer`, este vindo do cabeçalho `Referer`. O `pais` fica vazio. A aplicação só faz `INSERT` nessa tabela.
- **Falhas de gravação do clique:** um contador na memória da aplicação, que volta a zero quando ela reinicia (Q-42).

### Como o `short_code` é gerado

Sete caracteres em Base62, cada um sorteado com o módulo `secrets` do Python, sem contador nem relógio (RN-01). Um script Lua grava o Hash e inclui o código no Set do cliente numa só operação, e só se a chave `link:{short_code}` ainda não existir. Em colisão, a aplicação sorteia outro código, até 5 vezes.

### O caminho de um clique

1. A aplicação lê `link:{short_code}` na réplica do Redis. Se o link não está lá, por ainda não ter sido copiado, ou se a réplica não responde, lê do master. A conexão com a réplica não faz novas tentativas: na primeira falha, a leitura vai ao master (Q-31).
2. Sem o link no master, responde `404`. Com `expira_em` já passado, responde `410` com uma página HTML de link expirado. Nos dois casos, nada é contado nem gravado (RN-03).
3. Caso contrário, responde `302`. Só depois que a resposta sai, a aplicação envia o clique ao Cassandra, sem esperar a confirmação, e executa `INCR contador:{short_code}` no master.
4. A gravação do clique tem tempo limite de 2 s (Q-41). Se ela falhar ou passar desse tempo, o clique é descartado, sem nova tentativa: a falha vai para o log, com o `short_code` e o erro, e soma 1 em `falhas_gravacao_clique`, em `GET /metricas` (RN-07). O contador do Redis soma mesmo assim.

O dispositivo sai do cabeçalho `User-Agent` (Q-37): `tablet` para iPad, tablets Android (Android sem `Mobile`) e User-Agent com `Tablet`; `mobile` para iPhone, celulares Android e demais User-Agent com `Mobi`; `desktop` para Windows, macOS, Linux e ChromeOS. Fica `outro` o User-Agent ausente, o de robôs e pré-visualizações de redes sociais (`bot`, `crawl`, `spider`, `facebookexternalhit`, `WhatsApp` e outros), o de `curl` e `wget` e o que não se encaixa em nenhuma regra.

### Erros

Respostas decididas no Q-40 e no RN-03 ([QUESTOES](../docs/requisitos/QUESTOES.md#respondidas)):

| Situação | Resposta | O que é gravado |
| --- | --- | --- |
| Campo obrigatório ausente ou vazio, URL que não começa com `http://` ou `https://` seguido de um host válido, URL com mais de 2.083 caracteres (limite do `HttpUrl` do Pydantic), `expira_em` que não é data ISO 8601 com hífens e fuso (`2026-12-25T23:59:59Z`) | `422` | Nada |
| `campanha_id` que não existe | `422` | Nada |
| Em `POST /links`, falha de gravação no Redis ou 5 colisões seguidas | `503`, sem `short_code` | Nada no MongoDB |
| Em `GET /r/{short_code}`, link que não existe | `404` | Nada |
| Em `GET /r/{short_code}`, link com `expira_em` no passado | `410`, com a página de link expirado | Nada |

A aplicação não confere se o `cliente_id` foi cadastrado, nem se a campanha é do mesmo cliente do link ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md#fora-de-escopo)).

## Como testar

Com os bancos de desenvolvimento no ar e o ambiente Python criado:

```sh
.venv/Scripts/python -m pytest app
```

Os testes usam o banco 15 do Redis, o banco `linkpulse_testes` do MongoDB e o keyspace `linkpulse_testes` do Cassandra. O Redis e o MongoDB esvaziam antes e depois de cada teste. O keyspace é criado na primeira execução, com o mesmo [esquema](../infra/cassandra/esquema.cql) da aplicação, e cada teste apaga no fim os cliques dos links que criou. Os clientes, links e cliques da demonstração, no banco 0, no banco `linkpulse` e no keyspace `linkpulse`, não mudam. Rode os testes com os volumes de desenvolvimento, e não com os do benchmark. A suíte leva cerca de 6 s.

| Arquivo | O que confere |
| --- | --- |
| [test_clientes.py](tests/test_clientes.py) | CA-1: o cliente cadastrado aparece na listagem, e um cliente gravado como a carga do benchmark grava, fora do Set `clientes`, não aparece; sem `nome`, `422` |
| [test_campanhas.py](tests/test_campanhas.py) | Os campos do documento da campanha, com `links` vazia; sem `cliente_id` ou `nome`, `422` |
| [test_links.py](tests/test_links.py) | CA-2: os campos do Hash do link e o Set do cliente. CA-3 e Q-40: pedidos rejeitados com `422`, sem nada gravado no Redis nem na campanha. CA-5: a colisão preserva o link existente e o novo link recebe outro código. CA-6: o código entra na lista `links` da campanha. RN-08: com a réplica, que recusa escritas, e com o Redis fora do ar, a resposta é `503` sem `short_code` e a campanha não muda |
| [test_short_code.py](tests/test_short_code.py) | CA-4: 10.000 códigos com 7 caracteres em Base62, sem dois seguidos que difiram só no último caractere |
| [test_redirecionamento.py](tests/test_redirecionamento.py) | CA-7: link sem `expira_em` responde `302` com a `url` gravada, com o relógio em 2100. CA-8: link expirado responde `410`, sem contador e sem linha no Cassandra. CA-9: código inexistente responde `404`. CA-10: link fora da réplica, num banco aonde a cópia não chega, e réplica fora do ar respondem `302`, lidos do master. CA-12: o clique vira uma linha com `short_code`, `clicado_em`, `clique_id`, dispositivo e referrer, e nenhum arquivo da aplicação tem `UPDATE`. CA-13: 50 acessos concorrentes somam exatamente 50 no contador e gravam 50 linhas. RN-07: com o Cassandra simulado fora do ar, a resposta continua `302`, a falha vai para o log e `GET /metricas` mostra 1. A classificação do dispositivo para 11 User-Agent |

O teste da réplica fora do ar não é o CA-11: ele usa uma porta sem servidor, e não a réplica do Compose derrubada. O CA-11 e o CA-14, com a réplica e o Cassandra de fato parados, entram nos testes de aceitação (RM-40).
