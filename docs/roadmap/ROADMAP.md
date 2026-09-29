# Roadmap

Plano de tarefas do LinkPulse. Cada tarefa tem uma issue no GitHub, com o marco como milestone; o andamento é o estado da issue. Regras de uso em [README.md](README.md).

## Marcos

| Marco | Escopo | Situação |
| --- | --- | --- |
| **M0 — Preparação** | Processo, requisitos, decisões e specs para desenvolvimento guiado por especificações | Em revisão |
| **M1 — Modelagem inicial** | Descrição do problema, modelagem e justificativa, conforme o checklist da [DISCIPLINA](../produto/DISCIPLINA.md) ([ADR-0011](../decisoes/ADR-0011-marco-1-so-documentacao.md)) | Em andamento; vencimento no AVA 29/09/2026 00:00 (enviar até a noite de 28/09) |
| **M2 — Sistema completo** | Aplicação funcional (stack em [ADR-0010](../decisoes/ADR-0010-stack-da-aplicacao.md)) e banco de Documentos para metadados de campanha — [README](../../README.md#roadmap) | Specs e implementação planejadas; data a confirmar (penúltima aula, antes da P2) |

Tarefas de código começam quando a spec correspondente estiver `Pronta`.

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
| RM-17 | Completar a SPEC-001 (redirecionamento) até o status Pronta | M2 | — | RM-16, RM-20 | [SPEC-001](../specs/SPEC-001-redirecionamento.md) sem bloqueios e revisada | [#17](https://github.com/BudaBecker/link-pulse/issues/17) |
| RM-18 | Escrever a SPEC-002 (criação de link) | M2 | — | RM-16, RM-20 | SPEC-002 cobre RF-01, RN-01, RN-02, RN-08 sem bloqueios | [#18](https://github.com/BudaBecker/link-pulse/issues/18) |
| RM-19 | Escrever a SPEC-003 (consultas de analytics e painel) | M2 | — | RM-16, RM-20 | SPEC-003 cobre RF-05, RF-06, RNF-03, RNF-06 sem bloqueios | [#19](https://github.com/BudaBecker/link-pulse/issues/19) |
| RM-20 | Decidir as questões abertas de modelagem e dados | M1 | — | RM-14 | Questões abertas de [QUESTOES.md](../requisitos/QUESTOES.md) respondidas ou adiadas; REQUISITOS.md atualizado | [#20](https://github.com/BudaBecker/link-pulse/issues/20) |
| RM-21 | Especificar metadados de campanha em banco de Documentos (Marco 2) | M2 | — | RM-16 | ADR-0007 aceita, requisitos M2 catalogados e spec criada | [#21](https://github.com/BudaBecker/link-pulse/issues/21) |
| RM-22 | Montar o PDF Marco1_LinkPulse_AsaNorte.pdf | M1 | — | RM-15 | PDF único cobrindo EN-01 a EN-10, com o nome exigido | [#22](https://github.com/BudaBecker/link-pulse/issues/22) |
| RM-23 | Preparar a apresentação de 3 a 5 minutos do Marco 1 | M1 | — | — | Roteiro de 3–5 min (problema, modelagem, justificativa, demo se houver) ensaiado | [#23](https://github.com/BudaBecker/link-pulse/issues/23) |
| RM-24 | Montar ambiente local com Redis (master + réplica) e Cassandra | M2 | — | RM-16 | Um comando sobe o ambiente com keyspace e `cliques_por_link` criados | [#24](https://github.com/BudaBecker/link-pulse/issues/24) |
| RM-25 | Implementar a SPEC-001 (redirecionamento) | M2 | — | RM-17, RM-24 | CA-1 a CA-7 verificados por teste; quebrar por passo do plano quando a spec estiver `Pronta` | [#25](https://github.com/BudaBecker/link-pulse/issues/25) |
| RM-26 | Implementar a SPEC-002 (criação de link) | M2 | — | RM-18, RM-24 | Critérios da SPEC-002 verificados por teste | [#26](https://github.com/BudaBecker/link-pulse/issues/26) |
| RM-27 | Implementar a SPEC-003 (analytics e painel) | M2 | — | RM-19, RM-24 | Critérios da SPEC-003 verificados por teste | [#27](https://github.com/BudaBecker/link-pulse/issues/27) |
