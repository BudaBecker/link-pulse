# Requisitos

O que o LinkPulse precisa fazer (RF), com que qualidade (RNF) e sob quais regras (RN). A pasta também guarda as dúvidas que ainda impedem fechar esses itens.

| Arquivo | Conteúdo |
| --- | --- |
| [REQUISITOS.md](REQUISITOS.md) | Catálogo de RF, RNF e RN, cada um com origem e critério verificável |
| [QUESTOES.md](QUESTOES.md) | Questões abertas (`Q-xx`) com propostas, e questões já respondidas com o link da resposta |

## Regras

- **Fato x proposta.** `REQUISITOS.md` só contém o que está na documentação de [produto](../produto/README.md) e [arquitetura](../arquitetura/README.md) ou o que o grupo decidiu em uma `Q-xx` respondida. Ideias novas entram primeiro em `QUESTOES.md`, na coluna "Proposta".
- **IDs são permanentes.** Use o próximo número livre e não renumere. Item abandonado recebe status `Descartado`.
- **Todo requisito tem critério verificável.** Se o valor ainda não foi decidido, use `[meta: Q-xx]` e abra a questão.
- **Rastreabilidade.** A coluna "Spec" liga o requisito à especificação que o implementa ([`../specs/`](../specs/README.md)); a spec lista os IDs que cobre.

## Fluxo de uma questão

```
Q-xx aberta → grupo decide → ADR em ../decisoes/ (se atravessar vários requisitos)
            → REQUISITOS.md atualizado → Q-xx movida para "Respondidas"
```
