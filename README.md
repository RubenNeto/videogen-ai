# 🎬 TikTok Video Generator

> **Gerador automático de vídeos TikTok com IA · 100% gratuito · Open Source**

Cria vídeos curtos para TikTok automaticamente usando uma arquitetura de múltiplos agentes de IA, sem qualquer custo obrigatório.

---

## ✨ Funcionalidades

| Funcionalidade | Detalhes |
|---|---|
| 🎯 Temas | Motivação, Curiosidades, Histórias, Factos, Tecnologia, Natureza, História, Saúde |
| ⏱️ Durações | 15s, 30s, 60s |
| 🎤 Vozes | PT/EN/ES/FR · Masculina/Feminina/Robótica |
| 🎨 Imagens | Pollinations.ai (zero config) · Stable Diffusion · HuggingFace |
| 💬 Legendas | Estilo TikTok, Neon, Clássico, Minimal |
| 🎵 Música | Música de fundo livre de direitos |
| 📦 Batch | Geração de múltiplos vídeos em lote |
| 📱 Formato | 1080×1920 (9:16 vertical) |

---

## 🏗️ Arquitetura Multi-Agente

```
┌─────────────────────────────────────────────────────────┐
│                   PIPELINE PRINCIPAL                     │
│                                                          │
│  [Input] → A1 → A2 → A3 → A4 → A5 → A6 → [Vídeo MP4] │
└─────────────────────────────────────────────────────────┘

A1: ScriptAgent    → LLM (Ollama/Groq) → Script viral estruturado
A2: SceneAgent     → Divide em cenas com timing e efeitos
A3: ImageAgent     → Pollinations/SD/HF → Imagem por cena
A4: VoiceAgent     → edge-tts/Piper/Coqui → Áudio MP3
A5: SubtitleAgent  → Whisper/Auto → Ficheiro .ASS animado
A6: VideoAssembler → FFmpeg → Vídeo 1080x1920 final
```

---

## 🚀 Instalação Rápida

### 1. Clona o repositório
```bash
git clone https://github.com/teu-user/tiktok-video-generator
cd tiktok-video-generator
```

### 2. Instala dependências Python
```bash
pip install -r requirements.txt
```

### 3. Instala FFmpeg

**Linux/Ubuntu:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
```
winget install ffmpeg
# ou descarrega em: https://ffmpeg.org/download.html
```

### 4. Configura LLM (escolhe 1)

**Opção A — Ollama (recomendado, 100% local):**
```bash
# Instala Ollama em: https://ollama.ai
ollama pull llama3
ollama serve
```

**Opção B — Groq (gratuito, sem instalação):**
```bash
# Cria conta em: https://console.groq.com
export GROQ_API_KEY="gsk_..."
```

### 5. Copia configuração
```bash
cp .env.example .env
# Edita .env com as tuas configurações
```

### 6. Inicia a aplicação

**Interface Web (recomendado):**
```bash
python app.py
# Abre: http://localhost:7860
```

**Linha de comandos:**
```bash
python cli.py --theme curiosidades --duration 30
```

---

## 📖 Uso

### Interface Web
1. Abre `http://localhost:7860`
2. Escolhe o tema, duração, voz e idioma
3. Clica em **"🚀 GERAR VÍDEO"**
4. Aguarda ~2-5 minutos
5. Descarrega o vídeo gerado!

### CLI
```bash
# Vídeo simples
python cli.py --theme motivacao --duration 30

# Com tópico específico
python cli.py --theme factos --duration 60 --topic "factos sobre o universo"

# Em inglês com voz masculina
python cli.py --theme curiosidades --duration 30 --language en --voice en_male

# Sem música
python cli.py --theme historias --duration 60 --no-music

# Batch (múltiplos vídeos)
python cli.py --batch templates/batch_example.json
```

### Python API
```python
from pipeline import VideoGenerationPipeline

pipe = VideoGenerationPipeline()

result = pipe.generate_video(
    theme="curiosidades",
    duration=30,
    voice_type="pt_female",
    language="pt",
    subtitle_style="tiktok",
    topic="factos sobre o oceano profundo",
    add_music=True
)

if result["success"]:
    print(f"✅ Vídeo: {result['video_path']}")
    print(f"📊 Duração: {result['duration_real']:.1f}s")
    print(f"💾 Tamanho: {result['size_mb']:.1f} MB")
```

---

## 🗂️ Estrutura do Projeto

```
tiktok_generator/
├── app.py                  # Interface web Gradio
├── cli.py                  # Interface CLI
├── pipeline.py             # Orquestrador principal
├── requirements.txt        # Dependências Python
├── .env.example            # Configurações de ambiente
│
├── config/
│   └── settings.py         # Todas as configurações
│
├── agents/
│   ├── agent1_script.py    # Geração de script (LLM)
│   ├── agent2_scenes.py    # Divisão em cenas
│   ├── agent3_images.py    # Geração de imagens (IA)
│   ├── agent4_voice.py     # Geração de voz (TTS)
│   ├── agent5_subtitles.py # Legendas sincronizadas
│   └── agent6_video.py     # Montagem com FFmpeg
│
├── queue/
│   └── video_queue.py      # Sistema de fila
│
├── assets/
│   ├── music/              # Músicas de fundo (.mp3)
│   └── fonts/              # Fontes personalizadas
│
├── templates/
│   └── batch_example.json  # Exemplo de batch
│
└── output/
    ├── videos/             # Vídeos gerados
    ├── images/             # Imagens geradas (cache)
    ├── audio/              # Áudios gerados (cache)
    └── logs/               # Logs por job
```

---

## 🎵 Adicionar Música de Fundo

Coloca ficheiros `.mp3` na pasta `assets/music/`:

```bash
# Descarrega músicas livres de direitos:
# https://pixabay.com/music/
# https://freemusicarchive.org/
# https://www.bensound.com/

# Exemplo:
assets/music/
├── upbeat_motivational.mp3
├── ambient_curiosity.mp3
└── epic_cinematic.mp3
```

---

## 🌐 Backends Gratuitos

### LLM (Script)
| Backend | Qualidade | Velocidade | Requer |
|---|---|---|---|
| Ollama + Llama3 | ⭐⭐⭐⭐⭐ | Lento (local) | Hardware |
| Groq | ⭐⭐⭐⭐⭐ | ⚡ Ultra-rápido | Conta grátis |
| OpenRouter | ⭐⭐⭐⭐ | Rápido | Conta grátis |

### Imagens
| Backend | Qualidade | Velocidade | Requer |
|---|---|---|---|
| Pollinations.ai | ⭐⭐⭐⭐ | Médio | Nada! |
| SD Local (A1111) | ⭐⭐⭐⭐⭐ | Rápido | GPU |
| HuggingFace | ⭐⭐⭐ | Lento | Token grátis |

### TTS (Voz)
| Backend | Qualidade | Velocidade | Requer |
|---|---|---|---|
| edge-tts | ⭐⭐⭐⭐⭐ | Rápido | Internet |
| Piper TTS | ⭐⭐⭐⭐ | ⚡ Ultra-rápido | Download modelo |
| Coqui TTS | ⭐⭐⭐ | Médio | Instalação |
| gTTS | ⭐⭐⭐ | Rápido | Internet |

---

## 🚀 Melhorias Futuras

- [ ] **Upload automático TikTok** — via TikTok Creator API
- [ ] **Trending Topics** — integração com Google Trends / Twitter
- [ ] **Personagens consistentes** — LoRA / IP-Adapter para SD
- [ ] **Efeitos de texto animados** — FFmpeg drawtext avançado
- [ ] **Templates guardados** — reutiliza configurações favoritas
- [ ] **Scheduler** — publica automaticamente em horas de pico
- [ ] **Analytics** — rastreia performance dos vídeos
- [ ] **Música viral** — integração Suno AI (quando disponível)
- [ ] **Multi-plataforma** — export para Instagram Reels, YouTube Shorts

---

## 📄 Licença

MIT License — Uso livre, incluindo comercial.

---

## 🤝 Contribuições

PRs são bem-vindos! Abre uma issue para discutir melhorias.
