-- Esquema do PostgreSQL no LinkPulse, usado só pelo benchmark SQL x NoSQL.
--
-- O PostgreSQL é a base de comparação: estas tabelas guardam os mesmos links,
-- contadores e cliques que o Redis e o Cassandra, para as mesmas operações
-- serem medidas nos dois lados (docs/decisoes/ADR-0014). A imagem oficial roda
-- este arquivo só na primeira subida, com o volume vazio (docker-compose.yml).
--
-- Sem chave estrangeira e sem índice além das chaves primárias: o Redis e o
-- Cassandra não conferem se o link existe nem mantêm índices extras, e o
-- PostgreSQL não deve fazer trabalho a mais que o outro lado.

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

-- A chave primária composta serve à consulta por período, como a partição
-- ordenada do Cassandra.
CREATE TABLE cliques (
  short_code   text NOT NULL,
  clicado_em   timestamptz NOT NULL,
  clique_id    uuid NOT NULL,
  pais         text,
  dispositivo  text,
  referrer     text,
  PRIMARY KEY (short_code, clicado_em, clique_id)
);
