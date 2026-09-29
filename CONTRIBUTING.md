# Como contribuir

Regras práticas para o time do LinkPulse. O objetivo é que qualquer mudança seja fácil de revisar e rastreável até um requisito.

## Antes de começar

1. Leia o [README](README.md) e o [índice da documentação](docs/README.md).
2. Veja se a mudança já tem tarefa no [roadmap](docs/roadmap/README.md) ou issue aberta.
3. Comportamento novo precisa de uma [spec](docs/specs/README.md) `Pronta`. Uma correção que restaura comportamento já especificado usa a spec existente e uma issue de bug; se faltar especificação para o comportamento esperado, prepare e aprove a spec antes de codificar. Refatoração sem mudança de comportamento, documentação e processo não precisam de spec.

## Issues

Abra uma issue para todo trabalho que leve mais que alguns minutos. Use um dos modelos:

| Modelo | Quando usar |
| --- | --- |
| **Tarefa** | Trabalho planejado: implementar um passo de spec, escrever documentação, ajustar processo |
| **Bug** | Comportamento diferente do que um requisito ou spec descreve |
| **Questão / decisão** | Dúvida ou contradição que precisa de decisão do grupo (vira uma `Q-xx` em [QUESTOES.md](docs/requisitos/QUESTOES.md)) |

Uma boa issue diz **o que** e **como saber que terminou**, e cita os IDs relacionados (`RF-02`, `SPEC-001`, `Q-06`).

## Branches

A `main` é sempre a versão revisada. Nunca faça commit direto nela.

Formato: `tipo/numero-da-issue-descricao-curta`, em minúsculas e com hífens.

| Tipo | Uso | Exemplo |
| --- | --- | --- |
| `feat` | Funcionalidade nova | `feat/12-redirecionamento` |
| `fix` | Correção de bug | `fix/15-link-expirado-redireciona` |
| `docs` | Só documentação | `docs/8-requisitos-iniciais` |
| `chore` | Processo, configuração, ferramentas | `chore/9-templates-github` |

Sem issue, omita o número: `docs/ajusta-readme`.

## Commits

Siga o padrão já usado no histórico: **inglês, verbo no imperativo, minúsculas, sem ponto final**, até ~72 caracteres.

```
add redirect handler for short codes
fix expired link returning 302
update requirements after Q-06 decision
```

- Um commit, uma ideia. Evite "misc fixes".
- Use o corpo da mensagem para explicar o *porquê* e citar referências:

  ```
  fix expired link returning 302

  expira_em was compared as string instead of timestamp.
  Refs: #15, RN-03, SPEC-001
  ```

## Pull requests

- **Pequeno e com um propósito.** Se a descrição precisa de "e também", provavelmente são dois PRs.
- **Título** no mesmo padrão dos commits; ele vira a mensagem do squash.
- **Descrição** pelo [modelo](.github/pull_request_template.md): issue (`Closes #N`), spec, IDs de requisito e como foi verificado.
- **Documentação junto.** Se o PR muda comportamento, atualiza no mesmo PR: [REQUISITOS.md](docs/requisitos/REQUISITOS.md) (status/coluna "Spec"), a spec (critérios marcados) e, se for o caso, um ADR em [docs/decisoes/](docs/decisoes/README.md).
- Abra como **rascunho** (*draft*) enquanto não estiver pronto para revisão.

## Revisão

Todo PR passa por **revisão obrigatória antes do merge**. A revisão pode ser feita por outro integrante, pelo próprio autor ou por um agente (por exemplo, `/code-review` no Claude Code), desde que fique registrada no PR.

- **Registro:** um comentário de revisão no PR dizendo quem (ou qual agente) revisou e o resultado. Na autorrevisão, o autor comenta depois de reler o diff completo.
- **O revisor confere:**
  1. o PR faz o que a issue/spec pede, e só isso;
  2. os critérios de aceitação citados foram verificados;
  3. requisitos, spec e ADRs afetados foram atualizados;
  4. os links da documentação continuam funcionando.
- Comentários bloqueantes pedem mudança; sugestões opcionais começam com `sugestão:`.
- Achados de uma revisão por agente são conferidos pelo autor: ele corrige ou responde cada um antes do merge.

## Merge

- **Squash merge** na `main`, depois da revisão registrada e com a conversa resolvida.
- **Branches mergeadas são apagadas automaticamente** pelo GitHub (*Settings → General → Automatically delete head branches*). Se a opção estiver desligada, apague a branch à mão logo após o merge.
- Nada de `push --force` na `main`.
- Recomendado: proteger a `main` (*Settings → Branches*) exigindo PR antes do merge. Não exija aprovação de outra pessoa, porque o GitHub não permite que o autor aprove o próprio PR e a autorrevisão é aceita.

## Agentes de código

Agentes seguem o [AGENTS.md](AGENTS.md), além destas regras.
