# Usa uma imagem oficial e leve do Python
FROM python:3.11-slim

# Mostra os logs do servidor em tempo real (docker compose logs -f)
ENV PYTHONUNBUFFERED=1

# Define a pasta de trabalho dentro do container
WORKDIR /app

# Copia apenas os arquivos da aplicação para dentro do container
COPY banco.py .
COPY servidor.py .
COPY index.html .
COPY style.css .

# Inicializa o banco SQLite (em /app/dados). Em execução, a pasta é substituída pelo volume do compose.
RUN python banco.py

# Expõe a porta 8000 (a mesma usada no servidor.py)
EXPOSE 8000

# Comando para iniciar o servidor quando o container arrancar
CMD ["python", "servidor.py"]
