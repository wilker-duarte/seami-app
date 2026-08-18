# ==========================================
# SEAMI Django Web - Production Dockerfile
# Python 3.11 Slim (Ambiente 100% no Container)
# ==========================================
FROM python:3.11-slim AS base

# Evita arquivos .pyc e envia logs diretamente para stdout/stderr sem buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências do sistema necessárias para PostgreSQL e compilação
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    netcat-traditional \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python no container
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Cria usuário não-root por segurança e estrutura de diretórios
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/staticfiles /app/media

# Copia código do projeto
COPY . /app/

# Ajusta permissões e script de entrada
COPY entrypoint.sh /entrypoint.sh
RUN dos2unix /entrypoint.sh && \
    chmod +x /entrypoint.sh && \
    chown -R appuser:appuser /app /entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
