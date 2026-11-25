# SPEC-004 — Aplicação do Marco 2

- **Status:** Concluída
- **Requisitos:** RF-01, RF-02, RF-03, RF-04, RF-05, RF-06, RF-07, RF-08, RF-09, RNF-01, RNF-02, RNF-03, RNF-05, RNF-06, RNF-07, RN-01, RN-02, RN-03, RN-04, RN-06, RN-07, RN-08
- **Decisões:** ADR-0002, ADR-0003, ADR-0004, ADR-0006, ADR-0007, ADR-0009, ADR-0012, ADR-0013, ADR-0014
- **Bloqueios:** nenhum

## Objetivo

Uma aplicação que cadastra clientes, cria links, redireciona, registra cada clique e mostra o painel, o suficiente para demonstrar o LinkPulse funcionando ao vivo ([ADR-0012](../decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md)). Incorpora o redirecionamento antes descrito na SPEC-001.

## Fora de escopo

- Edição e exclusão de clientes, links e campanhas.
- Login, isolamento por cliente (Q-13) e validações além das descritas aqui.
- Geolocalização do país (Q-14) e filtro de bots (Q-16).
- Fila ou nova tentativa para cliques que falharam ao gravar.
- Tratamento de falha parcial entre Redis e MongoDB na criação de link com campanha.
- Benchmark, gerador de carga e tela de testes ([SPEC-005](SPEC-005-testes-de-stress.md)).

## Comportamento

Os dados e as chaves estão em [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passos 4 e 5 e no [ADR-0014](../decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md).

### Cadastro de cliente

- `POST /clientes {nome}` grava o Hash `cliente:{cliente_id}` com o nome, inclui o `cliente_id` no Set `clientes` e responde `201` com o `cliente_id`.
- `GET /clientes` lista os clientes do Set `clientes`. Os clientes carregados para o benchmark não aparecem.
- O pedido sem `nome`, ou com `nome` vazio, é rejeitado com `422` e nada é gravado (Q-40).

### Campanha

- `POST /campanhas {cliente_id, nome, descricao?, tags?}` grava um documento no MongoDB e responde `201` com o `campanha_id`.
- O documento guarda `cliente_id`, `nome`, `descricao`, `tags` e a lista `links`, que começa vazia.
- O pedido sem `cliente_id` ou sem `nome` é rejeitado com `422` e nada é gravado (Q-40).
- `GET /campanhas?cliente_id=…` responde `200 [{campanha_id, nome, descricao, tags, links}]`, com as campanhas do cliente em ordem de nome, e lista vazia se não houver nenhuma; sem `cliente_id`, `422` (Q-50).

### Criação de link

`POST /links {url, cliente_id, canal?, expira_em?, campanha_id?}`:

1. Rejeita com `422` o pedido sem `url` válida (absoluta, `http` ou `https`, com host) ou sem `cliente_id`, com `expira_em` sem fuso, e o pedido com `campanha_id` que não existe (Q-40) ou que é de uma campanha de outro cliente (Q-55). Nada é gravado.
2. Gera um `short_code` de 7 caracteres em Base62 (letras maiúsculas, minúsculas e dígitos), a partir de uma fonte aleatória.
3. Grava `link:{short_code}` só se a chave ainda não existir. Em colisão, gera outro código e tenta de novo.
4. Inclui o `short_code` no Set `links:cliente:{cliente_id}`.
5. Se houver `campanha_id`, acrescenta o `short_code` à lista `links` da campanha.
6. Responde `201` com o `short_code` só depois da confirmação do Redis. Se a gravação no Redis falhar, ou se as novas tentativas depois de colisões se esgotarem, responde `503`, sem `short_code` (Q-40).

`GET /links?cliente_id=…` responde `200 [{short_code, url, canal, criado_em, expira_em, contador}]`, com os links do Set `links:cliente:{cliente_id}`, lidos do master, em ordem decrescente de `criado_em`. `contador` é o valor de `contador:{short_code}`, `0` antes do primeiro clique; `canal` e `expira_em` vêm nulos quando o link não os tem. Cliente sem links dá lista vazia; sem `cliente_id`, `422` (Q-54).

### Redirecionamento

`GET /r/{short_code}`:

1. Lê `link:{short_code}` na réplica do Redis com `HGETALL`.
2. Se o link não estiver na réplica, ou se a réplica não responder, lê do master. A conexão com a réplica tem tempo limite de 0,25 s, para uma réplica parada não atrasar o redirecionamento (Q-61).
3. Se o link não existe no master, responde `404`. Se `expira_em` está no passado, responde `410` com a página de expiração. Nos dois casos, não soma no contador nem grava evento.
4. Caso contrário, responde `302` com `Location: {url}`.
5. Depois da resposta, executa `INCR contador:{short_code}` no master e grava o evento em `cliques_por_link`, de forma assíncrona e com tempo limite de 2 s (Q-41).
6. O evento leva `short_code`, `clicado_em`, `clique_id`, `dispositivo` (derivado do cabeçalho `User-Agent`: `mobile`, `desktop`, `tablet` ou `outro`, que inclui bots e User-Agent ausente) e `referrer`. O campo `pais` fica vazio.
7. Se a gravação do evento falhar, o clique é descartado, a falha é registrada em log e soma em um contador de falhas, guardado na memória da aplicação e exposto em `GET /metricas` como `{"falhas_gravacao_clique": n}` (Q-42). A resposta já enviada não muda.
8. Depois de uma queda do Cassandra, o driver reconecta sozinho, com no máximo 2 s entre as tentativas e sem desistir, para a gravação voltar logo depois do Cassandra (Q-66).

### Consultas e painel

- As quatro consultas de analytics recebem `inicio` e `fim` na query string, em ISO 8601 com fuso, e contam os cliques do intervalo fechado `[inicio, fim]` (Q-45):
  - `GET /analytics/por-dia?short_code=…` responde `{short_code, dias: [{dia, cliques}]}`, com um item para cada dia que o intervalo toca, em `AAAA-MM-DD` e em ordem crescente, e `0` nos dias sem clique (Q-46). Os dias são os do horário de Brasília (`America/Sao_Paulo`), e os instantes continuam gravados em UTC (Q-47).
  - `GET /analytics/por-canal?cliente_id=…` lê os links do Set `links:cliente:{cliente_id}` e o `canal` de cada um, e responde `{cliente_id, canais: [{short_code, canal, cliques}]}`, com todos os links do cliente, inclusive os sem clique, e `canal` nulo no link sem canal, em ordem decrescente de cliques e, no empate, de `short_code` (Q-46).
  - `GET /analytics/por-dispositivo?short_code=…` responde `{short_code, dispositivos: [{dispositivo, cliques}]}`, sempre com as quatro categorias, na ordem `mobile`, `desktop`, `tablet` e `outro`, e `0` nas que não têm clique (Q-49).
  - `GET /analytics/total?short_code=…` responde `{short_code, cliques}` (Q-46).
- O pedido sem `short_code`, `cliente_id`, `inicio` ou `fim`, com data sem fuso ou com `inicio` depois de `fim` é rejeitado com `422`. Um `short_code` que não existe no Redis responde `404`; um cliente sem links, `200` com `canais` vazia (Q-48).
- Cada consulta ao Cassandra informa a partition key e não usa `ALLOW FILTERING`.
- A tela da aplicação é uma página HTML servida pela própria aplicação em `GET /`, com os seus arquivos e o Chart.js em `/static/` (Q-54). Ela permite escolher ou cadastrar um cliente, cadastrar campanhas, criar links, e ver o total de cliques, os cliques por dia e por dispositivo de um link e a comparação entre os canais do cliente. Quando o link pertence a uma campanha, a tela mostra a descrição e as tags; ela acha a campanha na lista de `GET /campanhas` cuja lista `links` contém o link (Q-50).
- A janela da tela são os 7 dias de Brasília até o fechamento, 5 s antes do momento da leitura: `inicio` à 00:00 de 6 dias antes do dia do fechamento e `fim` no próprio fechamento (Q-53, Q-57). O total da janela vem de `GET /analytics/total`; ao lado, a tela mostra o `contador` do link como cliques desde a criação, que pode ser maior que o histórico (Q-51).
- A tela refaz as consultas do link e do cliente sozinha a cada 5 s, sem recarregar a página, e mostra a hora da última atualização (Q-52).
- A tela só publica um conjunto coerente: o total, a soma dos cliques por dia, a soma dos dispositivos e os cliques do link na comparação por canal são iguais. Se não forem, refaz as quatro consultas, com até 3 leituras no total por ciclo, e, se ainda não baterem, avisa e mantém os dados anteriores até o ciclo seguinte (Q-56).

## Plano de implementação

Stack em [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md).

1. Ambiente: Docker Compose com Redis (master e réplica), Cassandra com o keyspace e `cliques_por_link`, MongoDB e PostgreSQL, com os tetos definidos.
2. Cadastro de cliente, campanha e criação de link.
3. Redirecionamento, contador e gravação assíncrona do clique, com o tratamento de falha.
4. Consultas de analytics.
5. Tela da aplicação.
6. Testes de aceitação, incluindo os cenários com a réplica do Redis e o Cassandra indisponíveis.

## Critérios de aceitação

- [x] **CA-1** (RF-08) — Dado um nome, quando envio `POST /clientes`, então recebo `201` com um `cliente_id`, e esse cliente aparece em `GET /clientes`.
- [x] **CA-2** (RF-01, RN-08) — Dada uma URL válida e um `cliente_id`, quando envio `POST /links`, então recebo `201` com o `short_code`; `link:{short_code}` contém `url`, `cliente_id` e `criado_em`, e o código está em `links:cliente:{cliente_id}`.
- [x] **CA-3** (RN-02) — Dado um pedido sem `cliente_id`, quando envio `POST /links`, então o pedido é rejeitado e nada é gravado no Redis.
- [x] **CA-4** (RN-01) — Dados 10.000 códigos gerados em sequência, então todos têm 7 caracteres em Base62 e não há dois consecutivos que difiram só no último caractere.
- [x] **CA-5** (RN-01) — Dado um `short_code` gerado que já existe, quando o link é criado, então o link existente não é alterado e o novo link recebe outro código.
- [x] **CA-6** (RF-09) — Dada uma campanha existente, quando crio um link com o seu `campanha_id`, então o `short_code` passa a fazer parte da lista `links` do documento da campanha.
- [x] **CA-7** (RF-02, RN-04) — Dado um link existente sem `expira_em`, quando recebo `GET /r/{short_code}`, então a resposta é `302` com `Location` igual à `url` gravada, em qualquer data.
- [x] **CA-8** (RN-03, RF-07) — Dado um link com `expira_em` no passado, quando recebo `GET /r/{short_code}`, então a resposta é `410`, o contador não muda e nenhum evento é gravado.
- [x] **CA-9** (RN-03) — Dado um `short_code` inexistente, quando recebo `GET /r/{short_code}`, então a resposta é `404`.
- [x] **CA-10** (RF-02) — Dado um link gravado no master e ainda ausente na réplica, quando recebo `GET /r/{short_code}`, então a resposta é `302`.
- [x] **CA-11** (RNF-01) — Dada a réplica do Redis derrubada, quando recebo `GET /r/{short_code}` válido, então a resposta é `302`.
- [x] **CA-12** (RF-03, RN-06) — Dado um redirecionamento válido, quando o processamento assíncrono termina, então existe uma linha em `cliques_por_link` com aquele `short_code`, `clicado_em` e `clique_id`; nenhuma operação da aplicação executa `UPDATE` nessa tabela.
- [x] **CA-13** (RF-04, RNF-07) — Dados N acessos concorrentes a um link válido, quando todos terminam, então `contador:{short_code}` aumentou exatamente N.
- [x] **CA-14** (RNF-02, RN-07) — Dado o Cassandra indisponível, quando recebo `GET /r/{short_code}` válido, então a resposta continua `302`, a latência p95 medida no servidor fica abaixo de 50 ms e o contador de falhas aumenta.
- [x] **CA-15** (RF-05) — Dado um conjunto conhecido de eventos, quando executo as consultas por dia, por canal e total, então cada uma retorna exatamente as contagens esperadas.
- [x] **CA-16** (RNF-06, RNF-05) — A tabela declara `short_code` como partition key e `CLUSTERING ORDER BY (clicado_em DESC, clique_id DESC)`; nenhuma consulta CQL usa `ALLOW FILTERING`; o ambiente declara um master e uma réplica no Redis e um fator de replicação no keyspace.
- [x] **CA-17** (RF-06, RNF-03) — Dado um link com cliques, quando abro o painel, então vejo o total, os agregados por dia e por dispositivo e a comparação entre os canais do cliente, coerentes com as consultas do CA-15 e com a consulta por dispositivo; um clique novo aparece em até 60 s.
