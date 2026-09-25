# AGENTS.md

Instruções para agentes de código no LinkPulse. As regras humanas de issues, branches, commits e PRs estão no [CONTRIBUTING.md](CONTRIBUTING.md) e valem para você também.

Converse com o time em português do Brasil. Em perguntas e relatórios, descreva cada item por extenso; IDs como `RF-01` ou `Q-09` vão entre parênteses, como complemento.

## Estágio do projeto

O Marco 1 entrega só documentação: descrição do problema, modelagem e justificativa ([ADR-0011](docs/decisoes/ADR-0011-marco-1-so-documentacao.md), que substitui a [ADR-0008](docs/decisoes/ADR-0008-aplicacao-no-marco-1.md); checklist em [DISCIPLINA](docs/produto/DISCIPLINA.md)). A aplicação é do Marco 2, em Python + FastAPI com Redis e Cassandra via Docker Compose ([ADR-0010](docs/decisoes/ADR-0010-stack-da-aplicacao.md)). Para implementar comportamento novo, exija uma spec `Pronta`. Correções que restauram comportamento já especificado usam a spec existente; se o comportamento esperado não estiver especificado, prepare e aprove a spec antes de codificar. Refatorações sem mudança de comportamento, documentação e processo dispensam spec (regras em [docs/specs/](docs/specs/README.md)).

## Onde está cada coisa

| Preciso de... | Leia |
| --- | --- |
| Visão geral e índice | [docs/README.md](docs/README.md) |
| O que a disciplina exige em cada marco | [docs/produto/DISCIPLINA.md](docs/produto/DISCIPLINA.md) |
| O que o sistema deve fazer, com origem e critério | [docs/requisitos/REQUISITOS.md](docs/requisitos/REQUISITOS.md) |
| Dúvidas abertas que bloqueiam decisões | [docs/requisitos/QUESTOES.md](docs/requisitos/QUESTOES.md) |
| Por que algo foi decidido | [docs/decisoes/README.md](docs/decisoes/README.md) |
| Plano e critérios de aceitação de uma entrega | [docs/specs/README.md](docs/specs/README.md) |
| Tarefas e andamento | [docs/roadmap/README.md](docs/roadmap/README.md) |

Os documentos-fonte do Marco 1 são [VISAO](docs/produto/VISAO.md), [PITCH](docs/produto/PITCH.md), [ARQUITETURA](docs/arquitetura/ARQUITETURA.md) e [FUNCIONALIDADES](docs/arquitetura/FUNCIONALIDADES.md). Requisitos e ADRs citam seções deles como origem.

## Como executar uma tarefa

1. **Ancore a tarefa em IDs.** Identifique os requisitos (`RF-xx`, `RNF-xx`, `RN-xx`), a spec (`SPEC-NNN`) e as questões (`Q-xx`) envolvidos. Para documentação ou processo sem requisito de produto, identifique a tarefa ou issue correspondente; não invente IDs.
2. **Leia a origem.** Ao alterar uma afirmação sobre o produto, abra as seções citadas na coluna "Origem" dos requisitos afetados. Pronto quando cada afirmação de produto que você vai escrever tem uma frase de origem ou decisão registrada que a sustenta.
3. **Separe fato de proposta.** O que está nos documentos-fonte ou em decisões aceitas é fato do projeto. Uma nova meta, resposta HTTP, tecnologia ou regra de produto é proposta: registre-a como `Q-xx` em [QUESTOES.md](docs/requisitos/QUESTOES.md), na coluna "Proposta", e aguarde a decisão do usuário. Ajustes de documentação ou processo que não mudam o produto seguem [CONTRIBUTING.md](CONTRIBUTING.md), sem abrir uma questão de produto.
4. **Faça a mudança.** Edite o mínimo necessário e mantenha cada significado em um só lugar: aponte para o documento que já explica algo em vez de copiar o texto.
5. **Atualize a rastreabilidade** no mesmo conjunto de mudanças (ver abaixo).
6. **Valide** (ver abaixo) e relate o que verificou.

## Registrar decisões

- Decisão que atravessa vários requisitos (tecnologia, modelo de dados, topologia, escopo) → ADR em `docs/decisoes/` a partir do [modelo](docs/decisoes/_modelo.md), mais uma linha na tabela de registro.
- Decisão que fixa um único requisito (meta, código HTTP, campo) → atualize o requisito em REQUISITOS.md citando a `Q-xx` na origem.
- Em ambos os casos, mova a `Q-xx` para "Respondidas" em QUESTOES.md, com a resposta e o link.
- ADR aceito é imutável. Mudou de ideia: novo ADR, e o antigo passa a `Substituída por ADR-NNNN`.

## Rastreabilidade

- IDs são permanentes: use o próximo número livre; item abandonado recebe status `Descartado`.
- A spec lista os requisitos que cobre; a coluna "Spec" de REQUISITOS.md aponta de volta. Mantenha os dois lados iguais.
- Critério sem valor decidido usa `[meta: Q-xx]`, e a questão citada existe em QUESTOES.md.
- Commits e PRs citam os IDs (formato no CONTRIBUTING).

## Documentos-fonte do Marco 1

VISAO, PITCH, ARQUITETURA e FUNCIONALIDADES compõem a entrega do Marco 1 ([DISCIPLINA](docs/produto/DISCIPLINA.md)). Corrija um deles quando a correção tiver fundamento claro (documentação técnica oficial ou regra da disciplina) e registre a mudança no ADR ou na `Q-xx` correspondente. Sem fundamento claro, registre a inconsistência como `Q-xx`.

## Validação

Uma mudança está validada quando:

- todo link relativo em arquivos `.md` aponta para um arquivo existente (âncoras `#secao` incluídas);
- toda referência a requisito, questão, decisão ou spec (`RF-`, `RNF-`, `RN-`, `Q-`, `ADR-`, `SPEC-`) aponta para uma definição existente; padrões de modelo (`RF-xx`, `SPEC-NNN`) não são IDs, e uma spec futura pode ser citada no [ROADMAP.md](docs/roadmap/ROADMAP.md) antes de ter arquivo apenas se houver ali uma tarefa para criá-la;
- a coluna "Spec" de REQUISITOS.md e o campo "Requisitos" das specs concordam;
- cada nova pasta em `docs/` tem um `README.md` e aparece em [docs/README.md](docs/README.md).

## Commits e autoria

- O autor dos commits é sempre o usuário. Use a identidade git já configurada e mensagens sem trailers de coautoria (`Co-authored-by`).
- Antes de criar qualquer commit, mostre ao usuário o resumo das alterações e espere a aprovação. O grupo edita arquivos em paralelo: adicione ao commit só os arquivos que o usuário confirmou como prontos, um a um (nada de `git add -A`).
