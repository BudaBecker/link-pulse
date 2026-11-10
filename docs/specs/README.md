# Especificações

Uma especificação (spec) descreve **uma entrega implementável**: o comportamento esperado, o plano em passos pequenos e os critérios de aceitação. É o elo entre os [requisitos](../requisitos/README.md) e o código.

| Arquivo | Conteúdo |
| --- | --- |
| [_modelo.md](_modelo.md) | Modelo em branco |
| [SPEC-001-redirecionamento.md](SPEC-001-redirecionamento.md) | Redirecionamento de link curto (Substituída por SPEC-004) |
| [SPEC-004-aplicacao.md](SPEC-004-aplicacao.md) | Aplicação do Marco 2: clientes, links, redirecionamento, cliques e painel (Pronta) |
| [SPEC-005-testes-de-stress.md](SPEC-005-testes-de-stress.md) | Benchmark SQL x NoSQL: gerador de carga, cenários e tela de testes (Pronta) |
| SPEC-002, SPEC-003 | Descartadas antes de serem escritas: criação de link e analytics entraram na SPEC-004 |

## Como usar

1. **Escolha os requisitos.** Uma spec cobre um conjunto pequeno de RF/RNF/RN relacionados — o suficiente para uma entrega de poucos PRs.
2. **Copie o modelo** para `SPEC-NNN-titulo-curto.md` e preencha. Seja breve: a spec explica *o quê* e *como verificar*, não o código.
3. **Liste os bloqueios.** Toda dúvida vira uma `Q-xx` em [QUESTOES.md](../requisitos/QUESTOES.md) e aparece no campo "Bloqueios".
4. **Revise com o grupo.** Sem bloqueios e com critérios verificáveis, o status muda para `Pronta`.
5. **Quebre em tarefas.** Cada passo do plano vira uma tarefa no [roadmap](../roadmap/README.md).
6. **Implemente e feche.** Cada PR cita a spec; quando todos os critérios estiverem marcados, o status muda para `Concluída` e a coluna "Spec" em [REQUISITOS.md](../requisitos/REQUISITOS.md) é atualizada.

## Ciclo de status

```
Rascunho → Pronta → Em implementação → Concluída
```

Uma spec incorporada por outra recebe o status `Substituída por SPEC-NNN` e deixa de listar requisitos.

Uma spec em `Rascunho` pode ser escrita a qualquer momento. Implementação de comportamento novo só começa com a spec `Pronta`; correções de comportamento já coberto podem citar a spec existente mesmo se ela estiver `Concluída`.

## O que não precisa de spec

Correções que restauram comportamento já coberto por uma spec não precisam de **nova** spec: cite a existente e abra uma issue de bug. Se o comportamento esperado ainda não estiver especificado, prepare e aprove a spec antes de codificar. Refatorações sem mudança de comportamento, documentação e processo dispensam spec; uma issue basta.
