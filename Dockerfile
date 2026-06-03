FROM python:3.12-slim

WORKDIR /app

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libexpat1 \
        osmium-tool \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

# Diretório onde o arquivo de sessão do Instaloader será montado
# (ex: ~/.config/instaloader/ no host → /session no container)
VOLUME ["/session"]

ENV INSTALOADER_SESSION_DIR=/session

CMD ["python", "-m", "src.main"]
