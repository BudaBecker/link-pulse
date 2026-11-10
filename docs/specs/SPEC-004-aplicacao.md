# SPEC-004 — Aplicação do Marco 2

- **Status:** Pronta
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

### Campanha

- `POST /campanhas {cliente_id, nome, descricao?, tags?}` grava um documento no MongoDB e responde `201` com o `campanha_id`.
- O documento guarda `cliente_id`, `nome`, `descricao`, `tags` e a lista `links`, que começa vazia.

### Criação de link

`POST /links {url, cliente_id, canal?, expira_em?, campanha_id?}`:

1. Rejeita o pedido sem `url` válida ou sem `cliente_id`, e o pedido com `campanha_id` que não existe. Nada é gravado.
2. Gera um `short_code` de 7 caracteres em Base62 (letras maiúsculas, minúsculas e dígitos), a partir de uma fonte aleatória.
3. Grava `link:{short_code}` só se a chave ainda não existir. Em colisão, gera outro código e tenta de novo.
4. Inclui o `short_code` no Set `links:cliente:{cliente_id}`.
5. Se houver `campanha_id`, acrescenta o `short_code` à lista `links` da campanha.
6. Responde `201` com o `short_code` só depois da confirmação do Redis.

### Redirecionamento

`GET /r/{short_code}`:

1. Lê `link:{short_code}` na réplica do Redis com `HGETALL`.
2. Se o link não estiver na réplica, ou se a réplica não responder, lê do master.
3. Se o link não existe no master, responde `404`. Se `expira_em` está no passado, responde `410` com a página de expiração. Nos dois casos, não soma no contador nem grava evento.
4. Caso contrário, responde `302` com `Location: {url}`.
5. Depois da resposta, executa `INCR contador:{short_code}` no master e grava o evento em `cliques_por_link`, de forma assíncrona e com tempo limite curto.
6. O evento leva `short_code`, `clicado_em`, `clique_id`, `dispositivo` (derivado do cabeçalho `User-Agent`) e `referrer`. O campo `pais` fica vazio.
7. Se a gravação do evento falhar, o clique é descartado, a falha é registrada em log e soma em um contador de falhas que a aplicação expõe. A resposta já enviada não muda.

### Consultas e painel

- As três consultas de analytics: cliques por dia de um link, cliques por canal entre os links de um cliente e total de cliques em uma janela de tempo.
- Cada consulta ao Cassandra informa a partition key e não usa `ALLOW FILTERING`.
- A tela da aplicação é uma página HTML servida pela própria aplicação. Ela permite escolher ou cadastrar um cliente, criar links, e ver o total de cliques, os cliques por dia e por dispositivo de um link e a comparação entre os canais do cliente. Quando o link pertence a uma campanha, a tela mostra a descrição e as tags.

## Plano de implementação

Stack em [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md).

1. Ambiente: Docker Compose com Redis (master e réplica), Cassandra com o keyspace e `cliques_por_link`, MongoDB e PostgreSQL, com os tetos definidos.
2. Cadastro de cliente, campanha e criação de link.
3. Redirecionamento, contador e gravação assíncrona do clique, com o tratamento de falha.
4. Consultas de analytics.
5. Tela da aplicação.
6. Testes de aceitação, incluindo os cenários com a réplica do Redis e o Cassandra indisponíveis.

## Critérios de aceitação

- [ ] **CA-1** (RF-08) — Dado um nome, quando envio `POST /clientes`, então recebo `201` com um `cliente_id`, e esse cliente aparece em `GET /clientes`.
- [ ] **CA-2** (RF-01, RN-08) — Dada uma URL válida e um `cliente_id`, quando envio `POST /links`, então recebo `201` com o `short_code`; `link:{short_code}` contém `url`, `cliente_id` e `criado_em`, e o código está em `links:cliente:{cliente_id}`.
- [ ] **CA-3** (RN-02) — Dado um pedido sem `cliente_id`, quando envio `POST /links`, então o pedido é rejeitado e nada é gravado no Redis.
- [ ] **CA-4** (RN-01) — Dados 10.000 códigos gerados em sequência, então todos têm 7 caracteres em Base62 e não há dois consecutivos que difiram só no último caractere.
- [ ] **CA-5** (RN-01) — Dado um `short_code` gerado que já existe, quando o link é criado, então o link existente não é alterado e o novo link recebe outro código.
- [ ] **CA-6** (RF-09) — Dada uma campanha existente, quando crio um link com o seu `campanha_id`, então o `short_code` passa a fazer parte da lista `links` do documento da campanha.
- [ ] **CA-7** (RF-02, RN-04) — Dado um link existente sem `expira_em`, quando recebo `GET /r/{short_code}`, então a resposta é `302` com `Location` igual à `url` gravada, em qualquer data.
- [ ] **CA-8** (RN-03, RF-07) — Dado um link com `expira_em` no passado, quando recebo `GET /r/{short_code}`, então a resposta é `410`, o contador não muda e nenhum evento é gravado.
- [ ] **CA-9** (RN-03) — Dado um `short_code` inexistente, quando recebo `GET /r/{short_code}`, então a resposta é `404`.
- [ ] **CA-10** (RF-02) — Dado um link gravado no master e ainda ausente na réplica, quando recebo `GET /r/{short_code}`, então a resposta é `302`.
- [ ] **CA-11** (RNF-01) — Dada a réplica do Redis derrubada, quando recebo `GET /r/{short_code}` válido, então a resposta é `302`.
- [ ] **CA-12** (RF-03, RN-06) — Dado um redirecionamento válido, quando o processamento assíncrono termina, então existe uma linha em `cliques_por_link` com aquele `short_code`, `clicado_em` e `clique_id`; nenhuma operação da aplicação executa `UPDATE` nessa tabela.
- [ ] **CA-13** (RF-04, RNF-07) — Dados N acessos concorrentes a um link válido, quando todos terminam, então `contador:{short_code}` aumentou exatamente N.
- [ ] **CA-14** (RNF-02, RN-07) — Dado o Cassandra indisponível, quando recebo `GET /r/{short_code}` válido, então a resposta continua `302`, a latência p95 medida no servidor fica abaixo de 50 ms e o contador de falhas aumenta.
- [ ] **CA-15** (RF-05) — Dado um conjunto conhecido de eventos, quando executo as três consultas de analytics, então cada uma retorna exatamente as contagens esperadas.
- [ ] **CA-16** (RNF-06, RNF-05) — A tabela declara `short_code` como partition key e `CLUSTERING ORDER BY (clicado_em DESC, clique_id DESC)`; nenhuma consulta CQL usa `ALLOW FILTERING`; o ambiente declara um master e uma réplica no Redis e um fator de replicação no keyspace.
- [ ] **CA-17** (RF-06, RNF-03) — Dado um link com cliques, quando abro o painel, então vejo os agregados por dia e por dispositivo e a comparação entre os canais do cliente, coerentes com o CA-15; um clique novo aparece em até 60 s.
