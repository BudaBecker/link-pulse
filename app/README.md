# Aplicação do LinkPulse

API em Python com FastAPI que cadastra clientes e campanhas e cria links curtos ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md)), na stack do [ADR-0013](../docs/decisoes/ADR-0013-stack-e-ambiente-do-marco-2.md). Esta pasta tem o passo 2 do plano da spec, na tarefa de implementar o cadastro de cliente, campanha e criação de link (RM-36). O redirecionamento, o contador e a gravação dos cliques entram na tarefa seguinte (RM-37).

| Arquivo | O que tem |
| --- | --- |
| [main.py](main.py) | Monta a aplicação: abre as conexões e registra as rotas |
| [router.py](router.py) | As rotas, que chamam o service e devolvem 201, 422 ou 503 |
| [service.py](service.py) | O cadastro de clientes e campanhas, a criação de links e o sorteio do `short_code` |
| [models.py](models.py) | Os formatos dos pedidos, com a validação da URL e do `expira_em` |
| [tests/](tests/) | Os testes dos critérios CA-1 a CA-6 e das respostas de erro |

## Como rodar

A aplicação roda no computador, fora do Docker, e usa os bancos do [ambiente de desenvolvimento](../infra/README.md#como-usar).

1. Suba os bancos com os volumes de desenvolvimento: `docker compose up -d --wait`.
2. Crie o ambiente Python uma vez, na raiz do repositório:

   ```sh
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-testes.txt   # no Linux e no macOS: .venv/bin/python
   ```

3. Suba a API: `.venv/Scripts/python -m uvicorn app.main:app --port 8000`.

A documentação interativa das rotas fica em `http://127.0.0.1:8000/docs`. Por padrão, a aplicação usa o Redis master em `127.0.0.1:6379` e o MongoDB em `127.0.0.1:27017`, no banco `linkpulse`. Para mudar, use as variáveis `REDIS_MASTER_HOST`, `REDIS_MASTER_PORT`, `MONGO_URL` e `MONGO_DB`. O padrão é `127.0.0.1`, e não `localhost`, porque as portas do Compose só escutam em IPv4, e no Windows cada conexão a `localhost` espera cerca de 2 s pela tentativa em IPv6.

## Rotas

| Rota | Corpo | Resposta |
| --- | --- | --- |
| `POST /clientes` | `{nome}` | `201 {cliente_id}` |
| `GET /clientes` | — | `200 [{cliente_id, nome}]`, em ordem de nome |
| `POST /campanhas` | `{cliente_id, nome, descricao?, tags?}` | `201 {campanha_id}` |
| `POST /links` | `{url, cliente_id, canal?, expira_em?, campanha_id?}` | `201 {short_code}` |

Exemplo:

```sh
curl -X POST http://127.0.0.1:8000/links -H "content-type: application/json" \
  -d '{"url": "https://exemplo.com.br/natal", "cliente_id": "c1", "canal": "instagram"}'
```

### Onde cada dado fica

- **Cliente:** Hash `cliente:{cliente_id}` com o nome, e o `cliente_id` no Set `clientes`. A listagem lê só esse Set, e os clientes da base do benchmark ficam fora dele ([ADR-0014](../docs/decisoes/ADR-0014-modelo-de-dados-e-metodo-do-benchmark.md#dados-novos-da-aplicação)).
- **Campanha:** um documento na coleção `campanhas` do MongoDB, com `cliente_id`, `nome`, `descricao`, `tags` e `links`, que começa vazia. O `campanha_id` é o `_id` do documento.
- **Link:** Hash `link:{short_code}` com `url`, `cliente_id`, `criado_em` e, se informados, `canal` e `expira_em`. As datas ficam em UTC, no formato `2026-12-25T23:59:59.000Z`, o mesmo da base do benchmark. O código entra no Set `links:cliente:{cliente_id}` e, com `campanha_id`, no fim da lista `links` da campanha.

### Como o `short_code` é gerado

Sete caracteres em Base62, cada um sorteado com o módulo `secrets` do Python, sem contador nem relógio (RN-01). Um script Lua grava o Hash e inclui o código no Set do cliente numa só operação, e só se a chave `link:{short_code}` ainda não existir. Em colisão, a aplicação sorteia outro código, até 5 vezes.

### Erros

Respostas decididas no Q-40 ([QUESTOES](../docs/requisitos/QUESTOES.md#respondidas)):

| Situação | Resposta | O que é gravado |
| --- | --- | --- |
| Campo obrigatório ausente ou vazio, URL que não começa com `http://` ou `https://` seguido de um host válido, URL com mais de 2.083 caracteres (limite do `HttpUrl` do Pydantic), `expira_em` que não é data ISO 8601 com hífens e fuso (`2026-12-25T23:59:59Z`) | `422` | Nada |
| `campanha_id` que não existe | `422` | Nada |
| Em `POST /links`, falha de gravação no Redis ou 5 colisões seguidas | `503`, sem `short_code` | Nada no MongoDB |

A aplicação não confere se o `cliente_id` foi cadastrado, nem se a campanha é do mesmo cliente do link ([SPEC-004](../docs/specs/SPEC-004-aplicacao.md#fora-de-escopo)).

## Como testar

Com os bancos de desenvolvimento no ar e o ambiente Python criado:

```sh
.venv/Scripts/python -m pytest app
```

Os testes usam o banco 15 do Redis e o banco `linkpulse_testes` do MongoDB, que esvaziam antes e depois de cada teste. Os clientes e links da demonstração, no banco 0 e no banco `linkpulse`, não mudam. Rode os testes com os volumes de desenvolvimento, e não com os do benchmark. A suíte leva cerca de 3 s.

| Arquivo | O que confere |
| --- | --- |
| [test_clientes.py](tests/test_clientes.py) | CA-1: o cliente cadastrado aparece na listagem, e um cliente gravado como a carga do benchmark grava, fora do Set `clientes`, não aparece; sem `nome`, `422` |
| [test_campanhas.py](tests/test_campanhas.py) | Os campos do documento da campanha, com `links` vazia; sem `cliente_id` ou `nome`, `422` |
| [test_links.py](tests/test_links.py) | CA-2: os campos do Hash do link e o Set do cliente. CA-3 e Q-40: pedidos rejeitados com `422`, sem nada gravado no Redis nem na campanha. CA-5: a colisão preserva o link existente e o novo link recebe outro código. CA-6: o código entra na lista `links` da campanha. RN-08: com a réplica, que recusa escritas, e com o Redis fora do ar, a resposta é `503` sem `short_code` e a campanha não muda |
| [test_short_code.py](tests/test_short_code.py) | CA-4: 10.000 códigos com 7 caracteres em Base62, sem dois seguidos que difiram só no último caractere |
