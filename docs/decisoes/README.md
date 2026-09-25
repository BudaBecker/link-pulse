# Decisões

Registro das decisões arquiteturais e de produto (ADR — *Architecture Decision Record*). Um ADR responde "por que está assim?" para quem chegar depois.

## Quando registrar

Registre um ADR quando a escolha for difícil de desfazer e atravessar vários requisitos: tecnologia, modelo de dados, topologia, escopo de entrega. Uma decisão que só fixa o valor de um requisito (uma meta, um código HTTP) fica no próprio requisito em [REQUISITOS.md](../requisitos/REQUISITOS.md), com a `Q-xx` marcada como respondida. Detalhes de implementação que cabem num PR não precisam de ADR; regras do time ficam no [CONTRIBUTING](../../CONTRIBUTING.md).

## Como registrar

1. Copie [_modelo.md](_modelo.md) para `ADR-NNNN-titulo-curto.md`, com o próximo número livre.
2. Preencha com status `Proposta` e abra um PR (ou, se nasceu de uma questão, cite o `Q-xx`).
3. Quando o grupo aprovar, mude para `Aceita` e atualize a tabela abaixo.
4. Um ADR aceito não é reescrito. Se a decisão mudar, crie um ADR novo e marque o antigo como `Substituída por ADR-NNNN`.

## Registro

As decisões do Marco 1 já estão justificadas em [ARQUITETURA.md](../arquitetura/ARQUITETURA.md). Para não duplicar texto, elas aparecem aqui só como entradas que apontam para a seção de origem.

| ID | Decisão | Status | Onde está registrada |
| --- | --- | --- | --- |
| ADR-0001 | Adotar desenvolvimento guiado por especificações leve | Aceita | [ADR-0001](ADR-0001-desenvolvimento-guiado-por-especificacoes.md) |
| ADR-0002 | Separar responsabilidades: Redis (Chave-Valor) para redirecionamento e contador; Cassandra (Wide-Column) para histórico de cliques | Aceita (Marco 1) | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passos 2 a 5 |
| ADR-0003 | Gravar o evento de clique de forma assíncrona, depois da resposta `302` | Aceita (Marco 1) | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 3 |
| ADR-0004 | Priorizar disponibilidade (AP no CAP) e seguir o modelo BASE | Aceita (Marco 1) | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 6 §CAP e §BASE |
| ADR-0005 | Gerar `short_code` não sequencial e usá-lo como partition key (sharding hash-based) | Aceita (Marco 1) | [ARQUITETURA](../arquitetura/ARQUITETURA.md) Passo 5 e Passo 6 §Sharding |
| ADR-0006 | Redirecionar com HTTP `302` | Aceita (Marco 1), sem justificativa escrita | [FUNCIONALIDADES](../arquitetura/FUNCIONALIDADES.md) §Fluxo: redirecionamento |
| ADR-0007 | Usar banco de Documentos para metadados de campanha no Marco 2 | Proposta | [ARQUITETURA](../arquitetura/ARQUITETURA.md) §Próximo passo |
| ADR-0008 | Entregar uma aplicação funcional já no Marco 1 | Substituída por ADR-0011 | [ADR-0008](ADR-0008-aplicacao-no-marco-1.md) |
| ADR-0009 | Replicação Master-Slave no Redis e Master-Master no Cassandra | Aceita | [ADR-0009](ADR-0009-replicacao-por-banco.md) |
| ADR-0010 | Stack da aplicação: Python + FastAPI com Docker Compose | Aceita | [ADR-0010](ADR-0010-stack-da-aplicacao.md) |
| ADR-0011 | Marco 1 entrega só a documentação exigida; sistema completo no Marco 2 | Aceita | [ADR-0011](ADR-0011-marco-1-so-documentacao.md) |

## Decisões pendentes

As pendências abertas estão em [QUESTOES.md](../requisitos/QUESTOES.md).
