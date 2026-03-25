FROM python:3.11-slim

# Instala FFmpeg e dependências de sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /app

# Copia requirements e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do projeto
COPY . .

# Cria diretórios de output
RUN mkdir -p output/videos output/images output/audio output/logs \
    assets/music assets/fonts templates queue

# Expõe a porta do Gradio
EXPOSE 7860

# Variáveis de ambiente padrão
ENV PYTHONUNBUFFERED=1
ENV TTS_ENGINE=edge-tts
ENV SD_USE_LOCAL=false

# Comando de arranque
CMD ["python", "app.py"]
