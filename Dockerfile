FROM python:3.13.18-slim-bookworm

WORKDIR /linkpulse

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY infra/verificar_ambiente.py infra/
