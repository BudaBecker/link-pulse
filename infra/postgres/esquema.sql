-- Sem chave estrangeira nem índices além das chaves primárias (ADR-0014).

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
