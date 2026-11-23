-- Esquema do Cassandra no LinkPulse: o histórico de cliques de cada link.
--
-- O serviço cassandra-esquema do docker-compose.yml aplica este arquivo com o
-- cqlsh a cada subida; IF NOT EXISTS permite aplicá-lo de novo sem efeito.
-- O modelo está em docs/arquitetura/ARQUITETURA.md (Passo 5) e a chave, no
-- docs/decisoes/ADR-0014.
--
-- Keyspace é o equivalente no Cassandra a um banco de dados. O fator de
-- replicação diz em quantos nós cada dado fica: 1 aqui, porque o ambiente
-- local tem um nó só. Em produção seriam 3 (ADR-0013).

CREATE KEYSPACE IF NOT EXISTS linkpulse
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

-- Uma partição (grupo de linhas guardado junto) por short_code, com os
-- cliques do mais recente para o mais antigo: a consulta "cliques deste link
-- entre duas datas" lê uma só partição, já na ordem. clique_id (um timeuuid,
-- identificador único que carrega o instante) separa dois cliques do mesmo
-- link no mesmo milissegundo, que de outro modo se sobrescreveriam.
CREATE TABLE IF NOT EXISTS linkpulse.cliques_por_link (
  short_code   text,
  clicado_em   timestamp,
  clique_id    timeuuid,
  pais         text,
  dispositivo  text,
  referrer     text,
  PRIMARY KEY ((short_code), clicado_em, clique_id)
) WITH CLUSTERING ORDER BY (clicado_em DESC, clique_id DESC);
