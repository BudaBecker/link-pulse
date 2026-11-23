-- Esquema do Cassandra (ARQUITETURA Passo 5, ADR-0014).
-- Um nó local: fator de replicação 1. Em produção, 3 (ADR-0013).

CREATE KEYSPACE IF NOT EXISTS linkpulse
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS linkpulse.cliques_por_link (
  short_code   text,
  clicado_em   timestamp,
  clique_id    timeuuid,
  pais         text,
  dispositivo  text,
  referrer     text,
  PRIMARY KEY ((short_code), clicado_em, clique_id)
) WITH CLUSTERING ORDER BY (clicado_em DESC, clique_id DESC);
