# Regras da disciplina e entregas

Resumo das regras do projeto incremental de **Bancos de Dados NoSQL** (CEUB) que afetam o LinkPulse, com o que já está atendido pela documentação. A fonte é o documento "Projeto Incremental da Disciplina" distribuído pelo professor (arquivo `Regras_Projeto_NoSQL.pdf`, fora do repositório). Em caso de dúvida, vale o documento original.

## Visão geral

- Grupo de até 4 alunos; o mesmo grupo e o mesmo problema seguem do Marco 1 ao Marco 2.
- O projeto vale 40% da nota final (Marco 1 + Marco 2 + apresentação final).
- **Marco 1** — modelagem inicial + apresentação breve. Deve mobilizar as Unidades 1 a 3 (fundamentos, Chave-Valor, Wide-Column).
- **Marco 2** — sistema completo e funcional, integrando as famílias NoSQL do curso, com documentação e apresentação final.

O Marco 1 do LinkPulse entrega só a documentação exigida; a aplicação é entregue no Marco 2 ([ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md)).

## Marco 1 — checklist de entrega

Prazo: **29/09/2026 às 00:00** (vencimento no AVA) — na prática, o envio precisa acontecer até a noite de 28/09 ([Q-19](../requisitos/QUESTOES.md)). O documento de regras dizia 30/09 às 23h59 para o campus Asa Norte; vale o AVA.

| ID | Item exigido | Onde está atendido | Situação |
| --- | --- | --- | --- |
| EN-01 | Descrição do problema (2–3 páginas): contexto, requisitos principais, estimativa de volume | [VISAO](VISAO.md), [REQUISITOS](../requisitos/REQUISITOS.md), [ARQUITETURA](../arquitetura/ARQUITETURA.md) §Estimativa de volume | Conteúdo existe; conferir extensão ao montar o PDF |
| EN-02 | Modelagem inicial com diagramas ou exemplos concretos | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passos 4 e 5; [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) | Atendido |
| EN-03 | Justificativa: limites do relacional | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 2 | Atendido |
| EN-04 | Justificativa: CAP (CP ou AP), justificado pelo cenário | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §CAP | Atendido |
| EN-05 | Justificativa: ACID ou BASE, e por quê | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §BASE | Atendido |
| EN-06 | Justificativa: sharding (hash, range ou directory) e replicação (Master-Slave ou Master-Master) | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §Sharding e §Replicação | Atendido |
| EN-07 | Chave-Valor: quais dados usam o modelo e ao menos uma técnica estudada (estruturas do Redis, Consistent Hashing ou Vector Clocks) | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 4 (Hash, `INCR` e Set) | Atendido |
| EN-08 | Wide-Column: modelagem *query-first* | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passos 1 e 5 | Atendido |
| EN-09 | Wide-Column: definição de Column Families e, no Cassandra, partition key e clustering columns | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 5 | **Parcial**: partition key e clustering estão; o termo "Column Family" não é definido |
| EN-10 | Combinação de famílias explícita na justificativa | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Resumo e Passo 3 | Atendido |
| EN-11 | Um único PDF nomeado `Marco1_NomeDoGrupo_Campus.pdf` (aqui: `Marco1_LinkPulse_AsaNorte.pdf`) | — | Pendente |
| EN-12 | Upload no AVA, atividade "Marco 1 — Projeto Incremental" | — | Pendente (feito por um integrante) |
| EN-13 | Apresentação de 3 a 5 minutos em sala, no dia da entrega | — | Pendente |

## Marco 2 — o que será exigido

| ID | Item exigido | Situação |
| --- | --- | --- |
| EN-14 | Documentação final: modelagem e decisões de arquitetura com justificativa | Em construção ([decisões](../decisoes/README.md)) |
| EN-15 | Sistema funcional, demonstrável ao vivo (ou em vídeo) | Planejado; stack em [ADR-0010](../decisoes/ADR-0010-stack-da-aplicacao.md) |
| EN-16 | Apresentação de 10 a 12 minutos: problema, arquitetura, demonstração, lições aprendidas | Pendente |

Data do Marco 2: penúltima aula do semestre, antes da Prova 2 (a confirmar no cronograma da disciplina).
