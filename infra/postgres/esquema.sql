-- Esquema do PostgreSQL, só para o benchmark (ADR-0014).
-- Sem chave estrangeira e sem índice além das chaves primárias.

CREATE TABLE links (
  short_code  text PRIMARY KEY,
  url         text NOT NULL,
  cliente_id  text NOT NULL,
  canal       text,
  criado_em   timestamptz NOT NULL,
  expira_em   timestamptz
);

CREATE TABLE contadores (
  short_code  text PRIMARY KEY,
  total       bigint NOT NULL DEFAULT 0
);

CREATE TABLE cliques (
  short_code   text NOT NULL,
  clicado_em   timestamptz NOT NULL,
  clique_id    uuid NOT NULL,
  pais         text,
  dispositivo  text,
  referrer     text,
  PRIMARY KEY (short_code, clicado_em, clique_id)
);
