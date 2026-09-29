# Roadmap

Marcos e tarefas do LinkPulse. O plano fica neste repositório; o andamento fica nas issues do GitHub.

| Arquivo | Conteúdo |
| --- | --- |
| [ROADMAP.md](ROADMAP.md) | Marcos e tabela de tarefas (`RM-NN`), com tarefa pai, dependências, critério de conclusão e issue |

## Onde vive cada coisa

| Lugar | Fonte da verdade de |
| --- | --- |
| `ROADMAP.md` | Quais tarefas existem, origem, tarefa pai, dependências e "pronto quando" |
| Issues do GitHub | Andamento: uma issue por tarefa, com o marco como milestone, a tarefa pai como sub-issue e a coluna "Depende de" como dependência (*blocked by*) |
| [GitHub Project](https://github.com/users/BudaBecker/projects/1) | Visão em quadro das mesmas issues, com status, prioridade e prazo; espelha as issues e não guarda informação própria |

Andamento de uma tarefa: issue aberta → PR aberto com `Closes #N` (em revisão) → issue fechada pelo merge (concluída). Tarefa descartada tem a issue fechada como *not planned*.

## Como manter

- **Nova tarefa?** Adicione a linha em ROADMAP.md com o próximo `RM-NN` livre e abra a issue pelo modelo "Tarefa", com título `<tarefa> (RM-NN)` e o milestone do marco. Adicione a issue ao Project e registre as dependências.
- **Spec `Pronta`?** Cada passo do plano vira uma tarefa `RM-NN` e uma issue. Se já houver tarefa agregadora para implementá-la, mantenha o ID como tarefa pai (sub-issue) e feche-a depois das filhas.
- **Questão respondida?** As tarefas que ela bloqueava ficam liberadas.
- **Tarefa complementar?** Vira subtarefa da tarefa principal que ela completa (coluna "Pai" e sub-issue), no mesmo marco.

Prazos avaliados da disciplina ficam na tabela de marcos de ROADMAP.md e na data de vencimento do milestone.
