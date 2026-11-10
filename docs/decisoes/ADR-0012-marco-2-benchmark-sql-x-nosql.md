# ADR-0012 — Marco 2 entrega um benchmark SQL x NoSQL sobre uma aplicação simples

- **Status:** Aceita
- **Data:** 2026-11-10
- **Decidido por:** Gabriel Becker
- **Relacionados:** Q-24, Q-13, Q-14, ADR-0007, ADR-0011, ADR-0013, ADR-0014, RF-08 a RF-11, RNF-08, EN-14 a EN-16

## Contexto

O [ADR-0011](ADR-0011-marco-1-so-documentacao.md) deixou o sistema funcional para o Marco 2, e o plano anterior tratava a aplicação completa como a entrega principal. A apresentação final é em 25/11/2026, com 10 a 12 minutos ([DISCIPLINA](../produto/DISCIPLINA.md)). A justificativa do Marco 1 afirma que um banco relacional único não atende bem este padrão de acesso ([ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 2), mas essa afirmação nunca foi medida.

## Decisão

O resultado principal do Marco 2 é a **comparação medida entre os bancos NoSQL do projeto e o PostgreSQL**, usando as operações que o produto já faz. A aplicação fica com o necessário para demonstrar o sistema funcionando.

**Benchmark.** Quatro operações, cada uma contra o banco NoSQL escolhido para ela e contra uma versão equivalente no PostgreSQL:

| Operação | Lado NoSQL | Lado PostgreSQL |
| --- | --- | --- |
| Redirecionamento | Redis: `HGETALL link:{short_code}` | `SELECT` por chave primária |
| Contador | Redis: `INCR contador:{short_code}` | `UPDATE contadores SET total = total + 1` |
| Registro de clique | Cassandra: `INSERT` individual | `INSERT` individual |
| Histórico por período | Cassandra: leitura de uma partição | `SELECT` pela chave primária composta |

Três cenários: a comparação das quatro operações, o pico de tráfego concentrado em um link e a queda do Cassandra durante o pico. Uma tela própria inicia os testes e mostra os resultados. O método está no [ADR-0014](ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md).

**Aplicação.** Cinco funções: cadastrar cliente, criar link, redirecionar, registrar o clique e mostrar o painel. O banco de Documentos entra para a descrição e as tags das campanhas, o que aceita a proposta do ADR-0007.

**Fora do Marco 2:**

- edição e exclusão de clientes e links;
- login, isolamento por cliente e validações além das indispensáveis (Q-13 segue adiada);
- geolocalização: o país vem preenchido nos dados gerados e vazio nos cliques ao vivo (Q-14 segue adiada);
- benchmark do MongoDB;
- teste de escala do Cassandra em vários nós.

Os números são apresentados como saírem. Se o PostgreSQL vencer alguma operação, o resultado entra na apresentação com a explicação do motivo.

## Alternativas consideradas

- **Aplicação completa como entrega principal** — mais funcionalidades de produto, mas nenhuma evidência para a justificativa técnica, que é o que a disciplina avalia.
- **Benchmark sem aplicação** — não atende ao sistema funcional e demonstrável exigido no Marco 2 (EN-15).
- **Incluir o MongoDB no benchmark** — as operações comparadas são as do caminho de clique, que não passa pelo MongoDB; fica para depois, se houver tempo.

## Consequências

- O que os números permitem afirmar: como cada operação se comportou neste ambiente, com estes dados e limites. Eles não provam que um banco é melhor que outro em geral, nem como o Cassandra escala em vários nós.
- Entram requisitos de benchmark, tela de testes, cadastro de cliente e campanha em [REQUISITOS.md](../requisitos/REQUISITOS.md).
- Duas specs cobrem o Marco 2: [SPEC-004](../specs/SPEC-004-aplicacao.md) (aplicação) e [SPEC-005](../specs/SPEC-005-testes-de-stress.md) (testes de stress). A SPEC-001 passa a fazer parte da SPEC-004.
- A stack ganha PostgreSQL e MongoDB ([ADR-0013](ADR-0013-stack-e-ambiente-do-marco-2.md)).
- As tarefas do Marco 2 no [roadmap](../roadmap/ROADMAP.md) são refeitas.
