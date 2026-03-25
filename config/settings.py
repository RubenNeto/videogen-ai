"""
TikTok Video Generator - Configurações Globais
"""

import os
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
VIDEOS_DIR = OUTPUT_DIR / "videos"
IMAGES_DIR = OUTPUT_DIR / "images"
AUDIO_DIR = OUTPUT_DIR / "audio"
LOGS_DIR = OUTPUT_DIR / "logs"
ASSETS_DIR = BASE_DIR / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
FONTS_DIR = ASSETS_DIR / "fonts"
TEMPLATES_DIR = BASE_DIR / "templates"
QUEUE_DIR = BASE_DIR / "queue"

# Criar diretórios se não existirem
for d in [VIDEOS_DIR, IMAGES_DIR, AUDIO_DIR, LOGS_DIR, MUSIC_DIR, FONTS_DIR, TEMPLATES_DIR, QUEUE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Vídeo ────────────────────────────────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_FORMAT = "mp4"

# ─── Imagens ──────────────────────────────────────────────────────────────────
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1920

# Stable Diffusion (local via AUTOMATIC1111 ou via API gratuita)
# Opção 1: Local AUTOMATIC1111
SD_API_URL = os.getenv("SD_API_URL", "http://127.0.0.1:7860")
SD_USE_LOCAL = os.getenv("SD_USE_LOCAL", "true").lower() == "true"

# Opção 2: Pollinations.ai (completamente gratuito, sem chave)
POLLINATIONS_API = "https://image.pollinations.ai/prompt"

# Opção 3: Hugging Face Inference API (gratuito com registo)
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")
HF_MODEL = "stabilityai/stable-diffusion-2-1"

# ─── TTS ──────────────────────────────────────────────────────────────────────
# Opções: "piper", "coqui", "edge-tts" (gratuito online), "gtts"
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge-tts")

PIPER_VOICES_DIR = BASE_DIR / "voices" / "piper"
COQUI_MODEL = "tts_models/pt/cv/vits"

# edge-tts vozes (completamente gratuito, não precisa de conta)
EDGE_TTS_VOICES = {
    "pt_female": "pt-PT-RaquelNeural",
    "pt_male": "pt-PT-DuarteNeural",
    "en_female": "en-US-JennyNeural",
    "en_male": "en-US-GuyNeural",
    "es_female": "es-ES-ElviraNeural",
    "es_male": "es-ES-AlvaroNeural",
    "fr_female": "fr-FR-DeniseNeural",
    "fr_male": "fr-FR-HenriNeural",
    "robotic": "en-US-AriaNeural",  # Com SSML effect
}

# ─── LLM (Script) ─────────────────────────────────────────────────────────────
# Opção 1: Ollama local (llama3, mistral, etc.) - RECOMENDADO
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Opção 2: Groq (gratuito, muito rápido)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama3-70b-8192"

# Opção 3: OpenRouter (tem modelos gratuitos)
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
OPENROUTER_MODEL = "mistralai/mistral-7b-instruct:free"

# Hierarquia de fallback do LLM
LLM_PRIORITY = ["ollama", "groq", "openrouter", "local"]

# ─── Legendas ─────────────────────────────────────────────────────────────────
SUBTITLE_STYLES = {
    "tiktok": {
        "font_size": 72,
        "font_color": "white",
        "stroke_color": "black",
        "stroke_width": 4,
        "position": "center",
        "y_offset": 0.7,  # 70% da altura
        "words_per_line": 4,
        "highlight_color": "#FFD700",  # Dourado para palavra atual
        "bold": True,
        "uppercase": True,
    },
    "classic": {
        "font_size": 56,
        "font_color": "white",
        "stroke_color": "black",
        "stroke_width": 3,
        "position": "bottom",
        "y_offset": 0.9,
        "words_per_line": 6,
        "highlight_color": "#FFFFFF",
        "bold": False,
        "uppercase": False,
    },
    "neon": {
        "font_size": 68,
        "font_color": "#00FFFF",
        "stroke_color": "#FF00FF",
        "stroke_width": 3,
        "position": "center",
        "y_offset": 0.72,
        "words_per_line": 3,
        "highlight_color": "#FFFF00",
        "bold": True,
        "uppercase": True,
    },
    "minimal": {
        "font_size": 52,
        "font_color": "#F0F0F0",
        "stroke_color": "black",
        "stroke_width": 2,
        "position": "bottom",
        "y_offset": 0.88,
        "words_per_line": 7,
        "highlight_color": "#FF6B6B",
        "bold": False,
        "uppercase": False,
    },
}

# ─── Temas / Prompts ──────────────────────────────────────────────────────────
THEMES = {
    "motivacao": {
        "name": "Motivação",
        "emoji": "🔥",
        "script_tone": "energético, inspirador, direto",
        "image_style": "cinematic, dramatic lighting, motivational",
        "music": "upbeat_motivational",
    },
    "curiosidades": {
        "name": "Curiosidades",
        "emoji": "🤔",
        "script_tone": "intrigante, surpreendente, informativo",
        "image_style": "educational, colorful, dynamic",
        "music": "quirky_electronic",
    },
    "historias": {
        "name": "Histórias",
        "emoji": "📖",
        "script_tone": "narrativo, emocional, cativante",
        "image_style": "storytelling, cinematic, atmospheric",
        "music": "emotional_ambient",
    },
    "factos": {
        "name": "Factos Incríveis",
        "emoji": "⚡",
        "script_tone": "impactante, rápido, revelador",
        "image_style": "bold, graphic, scientific illustration",
        "music": "tense_electronic",
    },
    "tecnologia": {
        "name": "Tecnologia",
        "emoji": "🤖",
        "script_tone": "futurista, técnico mas acessível",
        "image_style": "futuristic, neon, cyberpunk, technology",
        "music": "electronic_future",
    },
    "natureza": {
        "name": "Natureza",
        "emoji": "🌿",
        "script_tone": "calmo, maravilhoso, contemplativo",
        "image_style": "nature photography, beautiful landscape, wildlife",
        "music": "nature_ambient",
    },
    "historia": {
        "name": "História",
        "emoji": "🏛️",
        "script_tone": "épico, dramático, educativo",
        "image_style": "historical, epic painting style, dramatic",
        "music": "epic_orchestral",
    },
    "saude": {
        "name": "Saúde & Bem-estar",
        "emoji": "💪",
        "script_tone": "prático, motivador, científico",
        "image_style": "clean, health, wellness, modern",
        "music": "calm_upbeat",
    },
}

# ─── Queue ────────────────────────────────────────────────────────────────────
MAX_QUEUE_SIZE = 50
MAX_CONCURRENT_JOBS = 2

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
