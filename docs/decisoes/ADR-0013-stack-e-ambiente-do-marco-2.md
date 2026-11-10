# ADR-0013 — Stack e ambiente do Marco 2

- **Status:** Aceita
- **Data:** 2026-11-10
- **Decidido por:** Gabriel Becker
- **Relacionados:** Q-25, Q-17, Q-21, ADR-0009, ADR-0010 (substituída), ADR-0012, ADR-0014, RF-06, RF-11, RNF-05, RNF-08

## Contexto

O [ADR-0010](ADR-0010-stack-da-aplicacao.md) definiu a stack para uma aplicação com Redis e Cassandra. O [ADR-0012](ADR-0012-marco-2-benchmark-sql-x-nosql.md) acrescenta o PostgreSQL como base de comparação, o MongoDB para as campanhas, um gerador de carga e uma tela de testes. A apresentação roda em um único computador, sem depender de internet.

## Decisão

**Linguagem e bibliotecas.** Continua Python com FastAPI, `redis-py` e `cassandra-driver`. Entram `psycopg` para o PostgreSQL e `pymongo` para o MongoDB.

**Telas.** A tela da aplicação e a tela de testes são HTML, CSS e JavaScript puros, sem framework e sem etapa de build. Os gráficos usam Chart.js, com o arquivo servido pela própria aplicação no lugar da CDN.

**Ambiente.** Um Docker Compose sobe tudo:

| Serviço | Papel | Teto |
| --- | --- | --- |
| Redis master + 1 réplica | links, contador, clientes | 2 CPUs e 2 GB no master |
| Cassandra, 1 nó | histórico de cliques | 2 CPUs e 2 GB, heap de 1 GB |
| PostgreSQL | só o benchmark | 2 CPUs e 2 GB |
| MongoDB | campanhas, fora do benchmark | definido ao montar o ambiente |
| Aplicação FastAPI | produto | definido ao montar o ambiente |
| Gerador de carga e tela de testes | benchmark | definido ao montar o ambiente |

Os três bancos comparados têm o mesmo teto. Se o Cassandra não suportar a carga de dados com 2 GB, o teto sobe nos três juntos.

**Configuração dos bancos.** Os três rodam com a configuração padrão da imagem oficial:

- PostgreSQL: todos os parâmetros no padrão;
- Redis: sem AOF, só com as fotografias periódicas da memória em disco (RDB);
- Cassandra: commit log periódico padrão, com o heap limitado para caber no teto.

A única execução fora do padrão é a curva extra do PostgreSQL com `synchronous_commit=off`, descrita no [ADR-0014](ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md).

**Gerador de carga.** Começa em Python, com vários processos. Se a calibração mostrar que ele usa 70% ou mais do seu limite de CPU já com 8 conexões, o laço que dispara as operações é reescrito em outra linguagem; a prevista é Rust. A coleta de métricas, a tela de testes e a aplicação continuam em Python. O resultado da calibração registra qual caminho foi seguido.

**Acesso ao Docker.** O contêiner do gerador recebe acesso ao Docker da máquina para parar e religar o Cassandra no cenário de queda. Um script manual fica como reserva.

## Alternativas consideradas

- **Ajustar o PostgreSQL** (por exemplo, `shared_buffers` em 25% da memória) — daria uma configuração mais próxima de produção, mas abriria a discussão sobre quais parâmetros ajustar em cada banco. Manter os três no padrão é a regra mais simples de explicar e de reproduzir.
- **Redis com AOF** — é a proposta para a durabilidade dos links (Q-17, adiada). Fica fora para manter a mesma regra do padrão nos três bancos; a garantia de cada um aparece ao lado dos números.
- **Gráficos por CDN** (ADR-0010) — a tela dependeria de internet durante a apresentação.
- **Gerador em Go** — também resolveria o gargalo; Rust é a preferência do grupo.
- **Derrubar o Cassandra à mão** — depende de alguém digitar o comando no segundo certo, durante a fala.

## Consequências

- Com um nó de Cassandra, o fator de replicação do keyspace é 1; o valor de produção (3) fica documentado, não executado.
- O acesso do gerador ao Docker é aceitável só neste ambiente local de apresentação.
- Sobra pouca memória fora dos três bancos: o consumo real é o primeiro ponto a medir quando o ambiente subir.
- Versões exatas de Python, das imagens e das bibliotecas são fixadas no primeiro PR de código (RM-24).
