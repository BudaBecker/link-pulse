# ADR-0010 — Stack da aplicação: Python + FastAPI com Docker Compose

- **Status:** Aceita
- **Data:** 2026-09-25
- **Decidido por:** Gabriel Becker
- **Relacionados:** Q-20, Q-21, ADR-0008, ADR-0009, RNF-05

## Contexto

O grupo vai entregar uma aplicação funcional já no Marco 1 ([ADR-0008](ADR-0008-aplicacao-no-marco-1.md)), com prazo curto. A aplicação precisa falar com Redis e Cassandra, servir o redirecionamento, a API de criação de links e um painel de analytics.

## Decisão

- **Linguagem e framework:** Python com FastAPI.
- **Acesso aos bancos:** `redis-py` para o Redis e `cassandra-driver` para o Cassandra.
- **Painel:** página HTML servida pela própria aplicação, com o gráfico desenhado por uma biblioteca carregada via CDN (Q-21).
- **Ambiente:** Docker Compose com Redis master + uma réplica (ADR-0009) e um nó de Cassandra. Com um único nó local, o fator de replicação do keyspace é 1; o valor de produção (3) fica documentado, não executado.

## Alternativas consideradas

- **Node.js (Express/Fastify)** — equivalente em capacidade. Python + FastAPI foi a proposta aceita: bibliotecas maduras para os dois bancos e documentação automática da API (Swagger), útil na apresentação.
- **Front-end separado para o painel** — mais trabalho de build e deploy sem ganho para a avaliação.

## Consequências

- Código de aplicação pode começar assim que a spec correspondente estiver `Pronta`.
- O teste de falha do RNF-01 (derrubar a réplica do Redis ou o Cassandra) roda no próprio Docker Compose.
- Versões exatas de Python e das bibliotecas são fixadas no primeiro PR de código (RM-24).
