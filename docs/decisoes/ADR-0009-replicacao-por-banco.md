# ADR-0009 — Replicação Master-Slave no Redis e Master-Master no Cassandra

- **Status:** Aceita
- **Data:** 2026-09-25
- **Decidido por:** Gabriel Becker
- **Relacionados:** Q-05, RNF-05, EN-06

## Contexto

A ARQUITETURA descrevia "replicação Master-Slave" para o sistema todo. O Cassandra, porém, não tem nó master: todos os nós aceitam escrita. O checklist da disciplina pede que a proposta escolha entre Master-Slave e Master-Master ([DISCIPLINA](../produto/DISCIPLINA.md), EN-06).

## Decisão

- **Redis:** Master-Slave. Escritas (criação de link, `INCR`) no master; leituras do redirecionador distribuídas entre réplicas.
- **Cassandra:** Master-Master (peer-to-peer), com fator de replicação definido por keyspace.

O texto foi corrigido em [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §Replicação.

## Alternativas consideradas

- **Manter "Master-Slave" para tudo** — tecnicamente incorreto para o Cassandra.
- **Master-Master também no Redis** — exige Redis Cluster ou soluções ativas-ativas, complexidade desnecessária para um dado lido muito mais do que escrito.

## Consequências

- Réplicas do Redis podem servir um mapeamento alguns instantes desatualizado, coerente com AP (ADR-0004).
- O fator de replicação do Cassandra e a quantidade de réplicas do Redis no ambiente da aplicação ficam para o ADR de stack.
