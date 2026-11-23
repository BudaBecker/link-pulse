# Imagem Python do LinkPulse, com as bibliotecas de acesso aos bancos nas
# versões fixadas em requirements.txt.
#
# É usada por dois serviços do Compose: `verificar` (docker-compose.yml),
# que confere o ambiente com infra/verificar_ambiente.py, e `carga`
# (docker-compose.benchmark.yml), que carrega e confere a base do benchmark e
# recebe a pasta benchmark/ montada, sem cópia na imagem. A versão do Python
# foi fixada na decisão de stack (docs/decisoes/ADR-0013).
FROM python:3.13.18-slim-bookworm

WORKDIR /linkpulse

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY infra/verificar_ambiente.py infra/
