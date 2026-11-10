# Roadmap

Plano de tarefas do LinkPulse. Cada tarefa tem uma issue no GitHub, com o marco como milestone; o andamento é o estado da issue. Regras de uso em [README.md](README.md).

## Marcos

| Marco | Escopo | Situação |
| --- | --- | --- |
| **M0 — Preparação** | Processo, requisitos, decisões e specs para desenvolvimento guiado por especificações | Concluído |
| **M1 — Modelagem inicial** | Descrição do problema, modelagem e justificativa, conforme o checklist da [DISCIPLINA](../produto/DISCIPLINA.md) ([ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md)) | Concluído |
| **M2 — Sistema completo** | Benchmark SQL x NoSQL sobre uma aplicação simples, com banco de Documentos para as campanhas ([ADR-0012](../decisoes/ADR-0012-marco-2-benchmark-sql-x-nosql.md); stack em [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md)) | Em andamento; apresentação em 25/11/2026 |

Tarefas de código começam quando a spec correspondente estiver `Pronta`. As tarefas RM-28 a RM-35 ainda não têm issue: elas são abertas, e as issues das tarefas descartadas são fechadas, quando o novo escopo do Marco 2 for aprovado.

## Tarefas

| ID | Tarefa | Marco | Pai | Depende de | Pronto quando | Issue |
| --- | --- | --- | --- | --- | --- | --- |
| RM-01 | Redigir CONTRIBUTING.md | M0 | — | — | [CONTRIBUTING.md](../../CONTRIBUTING.md) cobre issues, branches, commits, PRs, revisão e merge | [#1](https://github.com/BudaBecker/link-pulse/issues/1) |
| RM-02 | Criar templates de issue e PR em .github/ | M0 | RM-01 | RM-01 | Templates de tarefa, bug, questão e PR existem em `.github/` | [#2](https://github.com/BudaBecker/link-pulse/issues/2) |
| RM-03 | Redigir AGENTS.md | M0 | — | — | [AGENTS.md](../../AGENTS.md) cobre documentação, decisões, rastreabilidade e validação | [#3](https://github.com/BudaBecker/link-pulse/issues/3) |
| RM-04 | Descartado: tarefa pessoal, fora do repositório | M0 | — | — | — | [#4](https://github.com/BudaBecker/link-pulse/issues/4) |
| RM-05 | Criar estrutura leve de desenvolvimento guiado por especificações | M0 | — | — | `docs/requisitos/`, `docs/decisoes/`, `docs/specs/` com modelo, exemplo e instruções | [#5](https://github.com/BudaBecker/link-pulse/issues/5) |
| RM-06 | Documentar Requisitos Funcionais (RF) | M0 | RM-05 | — | RF com ID, origem e critério em [REQUISITOS.md](../requisitos/REQUISITOS.md) | [#6](https://github.com/BudaBecker/link-pulse/issues/6) |
| RM-07 | Documentar Requisitos Não Funcionais (RNF) | M0 | RM-05 | — | RNF com ID, origem e critério em [REQUISITOS.md](../requisitos/REQUISITOS.md) | [#7](https://github.com/BudaBecker/link-pulse/issues/7) |
| RM-08 | Documentar Regras de Negócio (RN) | M0 | RM-05 | — | RN com ID, origem e critério em [REQUISITOS.md](../requisitos/REQUISITOS.md) | [#8](https://github.com/BudaBecker/link-pulse/issues/8) |
| RM-09 | Separar fatos documentados de propostas e registrar dúvidas de inconsistência | M0 | RM-05 | RM-06, RM-07, RM-08 | Propostas e dúvidas só em [QUESTOES.md](../requisitos/QUESTOES.md) | [#9](https://github.com/BudaBecker/link-pulse/issues/9) |
| RM-10 | Atualizar README.md principal como porta de entrada | M0 | — | RM-11 | [README](../../README.md) liga aos índices e documentos | [#10](https://github.com/BudaBecker/link-pulse/issues/10) |
| RM-11 | Criar README.md em cada subpasta de docs/ | M0 | RM-10 | RM-05, RM-09 | Toda subpasta de `docs/` tem README ligado a [docs/README.md](../README.md) | [#11](https://github.com/BudaBecker/link-pulse/issues/11) |
| RM-12 | Descartado: tarefa pessoal, fora do repositório | M0 | — | — | — | [#12](https://github.com/BudaBecker/link-pulse/issues/12) |
| RM-13 | Organizar o roadmap inicial em issues e milestones do GitHub | M0 | — | RM-05, RM-09 | Toda linha desta tabela tem issue com o milestone do marco, e as sub-issues seguem a coluna "Pai" | [#13](https://github.com/BudaBecker/link-pulse/issues/13) |
| RM-14 | Decidir escopo, metas e fluxo de trabalho do projeto | M0 | — | — | Q-01 a Q-08 respondidas e registradas em [QUESTOES.md](../requisitos/QUESTOES.md) | [#14](https://github.com/BudaBecker/link-pulse/issues/14) |
| RM-15 | Conferir a documentação do Marco 1 contra as questões abertas | M1 | RM-22 | — | Checklist da [DISCIPLINA](../produto/DISCIPLINA.md) todo "Atendido" ou com correção decidida (EN-09, EN-01, Q-15) | [#15](https://github.com/BudaBecker/link-pulse/issues/15) |
| RM-16 | Registrar ADR de stack da aplicação | M1 | — | RM-14 | [ADR-0010](../decisoes/ADR-0010-stack-da-aplicacao.md) `Aceita` | [#16](https://github.com/BudaBecker/link-pulse/issues/16) |
| RM-17 | Descartado: o redirecionamento passou para a SPEC-004 (RM-28) | M2 | — | — | — | [#17](https://github.com/BudaBecker/link-pulse/issues/17) |
| RM-18 | Descartado: a criação de link passou para a SPEC-004 (RM-28) | M2 | — | — | — | [#18](https://github.com/BudaBecker/link-pulse/issues/18) |
| RM-19 | Descartado: as consultas de analytics e o painel passaram para a SPEC-004 (RM-28) | M2 | — | — | — | [#19](https://github.com/BudaBecker/link-pulse/issues/19) |
| RM-20 | Decidir as questões abertas de modelagem e dados | M1 | — | RM-14 | Questões abertas de [QUESTOES.md](../requisitos/QUESTOES.md) respondidas ou adiadas; REQUISITOS.md atualizado | [#20](https://github.com/BudaBecker/link-pulse/issues/20) |
| RM-21 | Descartado: as campanhas em banco de Documentos passaram para a SPEC-004 (RM-28) | M2 | — | — | — | [#21](https://github.com/BudaBecker/link-pulse/issues/21) |
| RM-22 | Montar o PDF Marco1_LinkPulse_AsaNorte.pdf | M1 | — | RM-15 | PDF único cobrindo EN-01 a EN-10, com o nome exigido | [#22](https://github.com/BudaBecker/link-pulse/issues/22) |
| RM-23 | Preparar a apresentação de 3 a 5 minutos do Marco 1 | M1 | — | — | Roteiro de 3–5 min (problema, modelagem, justificativa, demo se houver) ensaiado | [#23](https://github.com/BudaBecker/link-pulse/issues/23) |
| RM-24 | Montar o ambiente local com Redis (master + réplica), Cassandra, PostgreSQL e MongoDB | M2 | — | RM-28 | Um comando sobe o ambiente com os tetos do [ADR-0013](../decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md), o keyspace com `cliques_por_link` e o esquema do PostgreSQL criados; consumo de memória medido | [#24](https://github.com/BudaBecker/link-pulse/issues/24) |
| RM-25 | Descartado: o redirecionamento é implementado na RM-30 | M2 | — | — | — | [#25](https://github.com/BudaBecker/link-pulse/issues/25) |
| RM-26 | Descartado: a criação de link é implementada na RM-30 | M2 | — | — | — | [#26](https://github.com/BudaBecker/link-pulse/issues/26) |
| RM-27 | Descartado: o analytics e o painel são implementados na RM-30 | M2 | — | — | — | [#27](https://github.com/BudaBecker/link-pulse/issues/27) |
| RM-28 | Registrar o escopo do Marco 2 em decisões, requisitos e specs | M2 | — | — | ADR-0012 a ADR-0014 aceitas; [SPEC-004](../specs/SPEC-004-aplicacao.md) e [SPEC-005](../specs/SPEC-005-testes-de-stress.md) `Prontas`; requisitos e questões atualizados | a abrir |
| RM-29 | Carregar os dados de referência nos dois lados | M2 | — | RM-24 | CA-1 da [SPEC-005](../specs/SPEC-005-testes-de-stress.md) verificado | a abrir |
| RM-30 | Implementar a aplicação (SPEC-004) | M2 | — | RM-24, RM-28 | Critérios da [SPEC-004](../specs/SPEC-004-aplicacao.md) verificados por teste; quebrar por passo do plano | a abrir |
| RM-31 | Implementar o gerador de carga, a calibração e os cenários (SPEC-005) | M2 | — | RM-29 | CA-2 a CA-6 da [SPEC-005](../specs/SPEC-005-testes-de-stress.md) verificados; resultado da calibração registrado | a abrir |
| RM-32 | Implementar a tela de testes (SPEC-005) | M2 | — | RM-31 | CA-7 e CA-8 da [SPEC-005](../specs/SPEC-005-testes-de-stress.md) verificados | a abrir |
| RM-33 | Rodar as execuções completas e salvar o resultado | M2 | — | RM-30, RM-32 | Execução completa salva e aberta pela tela de testes; números conferidos pelo grupo | a abrir |
| RM-34 | Fechar a documentação final do Marco 2 | M2 | — | RM-33 | EN-14 atendido na [DISCIPLINA](../produto/DISCIPLINA.md): modelagem, decisões e resultados medidos, com as limitações do método | a abrir |
| RM-35 | Preparar o roteiro e ensaiar a apresentação de 10 a 12 minutos | M2 | — | RM-30, RM-33 | Roteiro com problema, arquitetura, demonstração e lições aprendidas, ensaiado dentro do tempo (EN-16) | a abrir |
