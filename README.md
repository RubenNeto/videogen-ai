# 🎬 VideoGen AI

Gera vídeos TikTok/Reels automaticamente com IA. Entra o niche, faz download do MP4.

**Stack:** FastAPI + SQLite + FFmpeg · Deploy no Railway com 1 clique

---

## Chaves necessárias (todas gratuitas)

| Serviço | Para quê | Custo | Link |
|---------|----------|-------|------|
| **Groq** | Scripts + IA (Llama 3.3-70B) | **Grátis** | [console.groq.com](https://console.groq.com) |
| **Pexels** | Fotos reais por niche | **Grátis** | [pexels.com/api](https://www.pexels.com/api/) |
| gTTS | Voz (automático) | **Grátis** | Sem chave |

> **Mínimo para funcionar: só a chave Groq** (30 segundos, sem cartão de crédito).

---

## Deploy no Railway

### Passo 1 — Obtém as chaves grátis

**Groq** (30 segundos):
1. Vai a [console.groq.com](https://console.groq.com)
2. Sign up com Google/GitHub
3. API Keys → Create API Key
4. Copia `gsk_...`

**Pexels** (recomendado, também grátis):
1. Vai a [pexels.com/api](https://www.pexels.com/api/)
2. Regista → "Your API Key"

---

### Passo 2 — GitHub

```bash
# Extrai o zip e entra na pasta
cd videogen-railway

git init
git add .
git commit -m "VideoGen AI initial commit"

# Vai a github.com → New repository → cria "videogen-ai"
git remote add origin https://github.com/SEU-USERNAME/videogen-ai.git
git branch -M main
git push -u origin main
```

---

### Passo 3 — Railway

1. Vai a [railway.app](https://railway.app) → **New Project**
2. **Deploy from GitHub repo** → seleciona `videogen-ai`
3. Railway deteta o `Dockerfile` → clica **Deploy Now**
4. Enquanto faz build, vai a **Variables** → Add Variable:

```
GROQ_API_KEY        = gsk_...
PEXELS_API_KEY      = (opcional mas recomendado)
VIDEO_QUALITY       = medium
VIDEOS_PER_RUN      = 3
```

5. Railway faz redeploy automático
6. Vai a **Settings** → **Networking** → **Generate Domain**
7. Abre o URL → app online! 🎉

---

## Testar localmente com Docker

```bash
# 1. Cria o .env com as tuas chaves
cp .env.example .env
# Edita .env: adiciona GROQ_API_KEY=gsk_...

# 2. Build e arrancar
docker-compose up --build

# 3. Abre http://localhost:8080
```

Sem Docker:
```bash
pip install -r backend/requirements.txt
# Mac: brew install ffmpeg   |   Linux: apt install ffmpeg
cp .env.example .env && nano .env
uvicorn backend.main:app --host 0.0.0.0 --port 8080
# Abre http://localhost:8080
```

---

## Como funciona

```
Tu: entras "Ford Mustang"
         ↓
┌──────────────────────────────────┐
│  7 Agentes IA (Groq Llama 3.3)  │
│                                  │
│  1. Analisa tendências TikTok    │
│  2. Estratégia de conteúdo       │
│  3. Escreve script com hook      │
│  4. Busca fotos reais (Pexels)   │
│  5. Gera voz (gTTS gratuito)     │
│  6. Monta vídeo 9:16 (FFmpeg)    │
│  7. Caption + hashtags           │
└───────────────┬──────────────────┘
                ↓
     MP4 pronto para download
  TikTok · Reels · Shorts · Feed
```

---

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `GROQ_API_KEY` | ✅ | Chave Groq grátis (ou usa GEMINI/OPENAI) |
| `GEMINI_API_KEY` | alternativa | Google Gemini grátis |
| `OPENAI_API_KEY` | alternativa paga | OpenAI GPT-4o-mini |
| `PEXELS_API_KEY` | recomendado | Fotos reais grátis |
| `ELEVENLABS_API_KEY` | opcional | Voz mais natural |
| `VIDEO_QUALITY` | não | `low` / `medium` / `high` (default: medium) |
| `VIDEOS_PER_RUN` | não | Nº vídeos por run (default: 3) |

---

## Formato dos vídeos gerados

- **Resolução:** 1080×1920 (9:16 vertical)
- **Codec:** H.264 + AAC
- **Legendas:** gravadas no vídeo
- **Duração:** 20–35 segundos
- **Compatível:** TikTok · Instagram Reels · YouTube Shorts · Facebook Reels
