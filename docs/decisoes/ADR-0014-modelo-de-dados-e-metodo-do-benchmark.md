# ADR-0014 — Modelo de dados do Marco 2 e método do benchmark

- **Status:** Aceita
- **Data:** 2026-11-10
- **Decidido por:** Gabriel Becker
- **Relacionados:** Q-26 a Q-30, Q-33, Q-34, ADR-0007, ADR-0012, ADR-0013, RF-03, RF-08, RF-09, RF-10, RNF-04, RNF-06, RNF-08

## Contexto

O benchmark do [ADR-0012](ADR-0012-marco-2-benchmark-sql-x-nosql.md) só vale se os dois lados fizerem o mesmo trabalho sobre os mesmos dados. Quatro pontos precisavam de decisão: um defeito na chave de `cliques_por_link`, o modelo do lado PostgreSQL, a diferença de garantia de gravação entre os bancos e a forma de aplicar a carga. O Marco 2 também acrescenta dados novos: clientes e campanhas.

## Decisão

### Cliques no mesmo milissegundo

A chave de `cliques_por_link` era `(short_code, clicado_em)`. No Cassandra, um `INSERT` com uma chave primária que já existe sobrescreve a linha, sem erro. Dois cliques do mesmo link no mesmo milissegundo viravam um só, e sob carga isso apagaria eventos em silêncio.

A tabela ganha `clique_id timeuuid` como segunda clustering column:

```sql
CREATE TABLE cliques_por_link (
  short_code   text,
  clicado_em   timestamp,
  clique_id    timeuuid,
  pais         text,
  dispositivo  text,
  referrer     text,
  PRIMARY KEY ((short_code), clicado_em, clique_id)
) WITH CLUSTERING ORDER BY (clicado_em DESC, clique_id DESC);
```

A consulta por período e a ordem do mais recente para o mais antigo não mudam (RNF-06).

### Modelo do lado PostgreSQL

```sql
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
```

- **Chave primária composta em `cliques`, sem índice extra.** O índice da chave primária já serve à consulta por período. O PostgreSQL mantém um índice só, como o Cassandra, que guarda os dados ordenados pela chave. Uma chave primária em `clique_id` mais um índice de consulta faria cada clique pagar dois índices.
- **Sem chave estrangeira.** O Redis e o Cassandra não conferem se o link existe ao gravar um clique. Com a chave estrangeira, o PostgreSQL faria uma leitura a mais por `INSERT`, e parte da diferença medida viria dessa conferência.
- **Configuração padrão**, conforme o [ADR-0013](ADR-0013-stack-e-ambiente-do-marco-2.md).

### Garantia de gravação

Cada banco confirma a escrita em um momento diferente:

| Banco e configuração | Quando confirma a escrita | O que se perde se a máquina cair |
| --- | --- | --- |
| PostgreSQL, padrão | depois de forçar a gravação em disco (`fsync`) | nada do que foi confirmado |
| PostgreSQL com `synchronous_commit=off` | antes do `fsync` | os últimos instantes |
| Cassandra, padrão | depois de escrever no commit log em memória; o `fsync` é periódico | até o intervalo do `fsync` periódico (10 s no padrão) |
| Redis, padrão | na memória; a fotografia RDB é periódica | o que foi escrito desde a última fotografia |

No padrão, o PostgreSQL faz mais trabalho por escrita que os outros dois. Para separar o efeito da garantia do efeito do modelo, as duas escritas (contador e registro de clique) rodam uma segunda vez no PostgreSQL com `synchronous_commit=off`. Essa **curva extra** aparece à parte, identificada como fora do padrão. Ao vivo, ela aparece só no registro de clique.

### Como a carga é aplicada

- **Laço fechado** nas quatro operações e no pico: um número fixo de conexões, e cada uma só envia a próxima operação quando a anterior responde. Mede a vazão máxima e a latência nela.
- **Laço aberto** na queda do Cassandra: 200 redirecionamentos por segundo, passando pela aplicação. A taxa constante permite comparar a latência antes, durante e depois da queda.
- **Calibração.** Antes das execuções completas, o gerador roda com 8, 32 e 64 conexões. Vale o maior número em que ele usa menos de 70% do seu limite de CPU. O mesmo número é usado nos dois lados e nas quatro operações.
- **Mesmas condições.** Um lado roda de cada vez, com os mesmos dados, o mesmo número de conexões e comandos preparados. Comparação, pico e histórico medem direto no banco; só a queda do Cassandra passa pela aplicação.

### Dados e durações

- **Dados carregados:** cerca de 150 clientes, 45 mil links e 10 milhões de cliques, iguais nos dois lados e espalhados por 90 dias. Um link popular concentra 20% dos cliques; o restante se divide por igual entre os outros links.
- **Sorteio dos links:** nas operações medidas, 20% das chamadas caem no link popular.
- **Histórico por período:** lê os cliques de um link nas últimas 24 horas dos dados carregados, com limite de 1.000 linhas.
- **Execução completa:** cada operação roda 60 s por lado, depois de 10 s de aquecimento descartados. A sequência repete 3 vezes e o número publicado é a mediana.
- **Execução ao vivo:** uma vez, em até 480 s, só para ilustrar. Os tempos de cada etapa estão na [SPEC-005](../specs/SPEC-005-testes-de-stress.md).
- **Queda do Cassandra:** o teste para o contêiner aos 30 s e o religa aos 60 s, em uma etapa de 90 s.

### Dados novos da aplicação

- **Clientes, no Redis:** Hash `cliente:{cliente_id}` com o nome, e Set `clientes` com os clientes da demonstração. Os clientes do benchmark ficam fora desse Set, e o seletor da tela mostra só os da demonstração.
- **Campanhas, no MongoDB:** um documento por campanha, com os links embutidos. Isso aceita a proposta do ADR-0007.

```json
{
  "cliente_id": "8842",
  "nome": "Black Friday 2026",
  "descricao": "Campanha de novembro",
  "tags": ["promo", "varejo"],
  "links": ["abc123", "def456", "ghi789"]
}
```

## Alternativas consideradas

- **Trocar `clicado_em` por um único `timeuuid`** — resolve a colisão, mas muda a coluna usada na consulta por período já documentada.
- **Chave estrangeira e índices extras no PostgreSQL** — modelo relacional mais completo, porém com trabalho que o lado NoSQL não faz.
- **Laço aberto em todas as operações** — mais realista para um site, mas exige escolher a taxa antes e é mais difícil de gerar sem o gerador virar o gargalo.
- **Um documento por link no MongoDB** — repete a descrição e as tags em cada link da campanha; é uma tabela relacional escrita em JSON.
- **Carga na referência do produto (500 cliques por minuto)** — equivale a cerca de 8 por segundo e não pressiona nenhum dos bancos.

## Consequências

- [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 5 é corrigida com a nova chave. O fundamento é o comportamento de sobrescrita do `INSERT` no Cassandra.
- O laço fechado esconde parte dos atrasos quando o banco trava (omissão coordenada). Essa limitação entra na apresentação junto com os números.
- A referência de 500 cliques por minuto (RNF-04) continua como volume esperado em operação; o critério do requisito passa a ser o cenário de pico.
- Parar e religar o Cassandra pode levar mais que os 30 s previstos para a volta. Isso é verificado na primeira execução do cenário.
