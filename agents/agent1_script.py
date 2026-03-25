"""
Agente 1: Gerador de Script
Gera scripts virais e envolventes para TikTok usando LLMs gratuitos
"""

import json
import logging
import re
import requests
from typing import Optional
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from config.settings import (
    OLLAMA_URL, OLLAMA_MODEL, GROQ_API_KEY, GROQ_MODEL,
    OPENROUTER_KEY, OPENROUTER_MODEL, LLM_PRIORITY, THEMES
)

logger = logging.getLogger(__name__)


class ScriptAgent:
    """Agente responsável por gerar scripts virais para TikTok."""

    def __init__(self):
        self.available_llm = self._detect_available_llm()
        logger.info(f"ScriptAgent inicializado com LLM: {self.available_llm}")

    def _detect_available_llm(self) -> str:
        """Deteta qual LLM está disponível."""
        for llm in LLM_PRIORITY:
            if llm == "ollama" and self._check_ollama():
                return "ollama"
            elif llm == "groq" and GROQ_API_KEY:
                return "groq"
            elif llm == "openrouter" and OPENROUTER_KEY:
                return "openrouter"
        return "fallback"

    def _check_ollama(self) -> bool:
        """Verifica se Ollama está a correr localmente."""
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _call_ollama(self, prompt: str, system: str = "") -> str:
        """Chama o Ollama local."""
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.85, "top_p": 0.9}
        }
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def _call_groq(self, prompt: str, system: str = "") -> str:
        """Chama a API gratuita do Groq."""
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
            "max_tokens": 2000
        }
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=payload, timeout=30
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_openrouter(self, prompt: str, system: str = "") -> str:
        """Chama o OpenRouter com modelos gratuitos."""
        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tiktok-generator.local"
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
        }
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers, json=payload, timeout=45
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_llm(self, prompt: str, system: str = "") -> str:
        """Chama o LLM disponível com fallback automático."""
        try:
            if self.available_llm == "ollama":
                return self._call_ollama(prompt, system)
            elif self.available_llm == "groq":
                return self._call_groq(prompt, system)
            elif self.available_llm == "openrouter":
                return self._call_openrouter(prompt, system)
            else:
                return self._fallback_script(prompt)
        except Exception as e:
            logger.warning(f"LLM primário falhou ({e}), tentando fallback...")
            return self._fallback_script(prompt)

    def _fallback_script(self, prompt: str) -> str:
        """Script de fallback quando nenhum LLM está disponível."""
        # Extrai tema do prompt
        tema = "curiosidades incríveis"
        for t in THEMES:
            if t in prompt.lower():
                tema = THEMES[t]["name"]
                break

        return json.dumps({
            "titulo": f"Facto Incrível sobre {tema}",
            "hook": f"Isto vai mudar a forma como pensas sobre {tema}!",
            "cenas": [
                {
                    "numero": 1,
                    "texto": f"Sabes algo incrível sobre {tema}?",
                    "duracao": 3,
                    "descricao_visual": f"dramatic close-up related to {tema}, cinematic"
                },
                {
                    "numero": 2,
                    "texto": "A maioria das pessoas nunca soube disto.",
                    "duracao": 3,
                    "descricao_visual": "mysterious atmosphere, dark background, spotlight"
                },
                {
                    "numero": 3,
                    "texto": "Partilha com quem precisa de saber!",
                    "duracao": 2,
                    "descricao_visual": "vibrant, social media style, call to action visual"
                }
            ],
            "call_to_action": "Segue para mais factos incríveis!",
            "hashtags": ["#viral", "#factos", "#curioso", "#aprende"]
        })

    def generate_script(
        self,
        theme: str,
        duration: int,
        language: str = "pt",
        topic: Optional[str] = None,
        job_id: str = ""
    ) -> dict:
        """
        Gera um script viral completo para TikTok.

        Args:
            theme: Tema do vídeo (ex: 'motivacao', 'curiosidades')
            duration: Duração em segundos (15, 30, 60)
            language: Idioma ('pt', 'en', 'es', 'fr')
            topic: Tópico específico (opcional)
            job_id: ID do job para logging

        Returns:
            Dict com script estruturado por cenas
        """
        logger.info(f"[{job_id}] Gerando script | tema={theme} | duração={duration}s | lang={language}")

        theme_config = THEMES.get(theme, THEMES["curiosidades"])
        num_scenes = max(3, duration // 5)  # ~5 segundos por cena
        topic_str = f"sobre '{topic}'" if topic else ""

        lang_map = {"pt": "Português", "en": "English", "es": "Español", "fr": "Français"}
        language_name = lang_map.get(language, "Português")

        system_prompt = f"""És um criador de conteúdo viral para TikTok especializado em vídeos de {duration} segundos.
O teu estilo é: {theme_config['script_tone']}.
Escreves em {language_name}.
REGRAS OBRIGATÓRIAS:
- Hook PODEROSO nos primeiros 3 segundos (faz a pessoa PARAR de scrollar)
- Frases CURTAS (máximo 10 palavras)
- Linguagem simples e direta
- Cria SUSPENSE e curiosidade
- Termina com call-to-action
- NUNCA uses palavrões ou conteúdo ofensivo
- Responde APENAS em JSON válido, sem markdown"""

        user_prompt = f"""Cria um script para um vídeo TikTok de {duration} segundos {topic_str}.
Tema: {theme_config['name']} ({theme_config['emoji']})
Tom: {theme_config['script_tone']}

Responde com este JSON exato (sem mais nada):
{{
  "titulo": "título interno do vídeo",
  "hook": "frase de abertura impactante (máx 8 palavras)",
  "cenas": [
    {{
      "numero": 1,
      "texto": "texto narrado nesta cena (máx 15 palavras)",
      "duracao": 5,
      "descricao_visual": "prompt em inglês para gerar imagem com IA (seja específico e visual)",
      "emocao": "curiosidade/surpresa/motivação/alegria"
    }}
  ],
  "call_to_action": "frase final de call-to-action",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"]
}}

Cria exatamente {num_scenes} cenas. Total de duração = {duration} segundos.
A soma das durações das cenas deve ser {duration}."""

        raw = self._call_llm(user_prompt, system_prompt)
        script = self._parse_script(raw, theme, duration, num_scenes)

        logger.info(f"[{job_id}] Script gerado: {len(script.get('cenas', []))} cenas")
        return script

    def _parse_script(self, raw: str, theme: str, duration: int, num_scenes: int) -> dict:
        """Parseia e valida o script gerado pelo LLM."""
        # Tenta extrair JSON do texto
        try:
            # Remove possíveis markdown code blocks
            clean = re.sub(r'```json?\s*', '', raw)
            clean = re.sub(r'```\s*', '', clean)

            # Encontra o JSON no texto
            match = re.search(r'\{[\s\S]*\}', clean)
            if match:
                script = json.loads(match.group())
            else:
                raise ValueError("JSON não encontrado")

            # Validação e correção
            script = self._validate_and_fix(script, theme, duration, num_scenes)
            return script

        except Exception as e:
            logger.warning(f"Erro ao parsear script: {e}. Usando script de fallback.")
            return json.loads(self._fallback_script(theme))

    def _validate_and_fix(self, script: dict, theme: str, duration: int, num_scenes: int) -> dict:
        """Valida e corrige o script."""
        theme_config = THEMES.get(theme, THEMES["curiosidades"])

        # Garante campos obrigatórios
        if "titulo" not in script:
            script["titulo"] = f"Vídeo {theme_config['name']}"
        if "hook" not in script:
            script["hook"] = "Isto vai surpreender-te!"
        if "call_to_action" not in script:
            script["call_to_action"] = "Segue para mais!"
        if "hashtags" not in script:
            script["hashtags"] = ["#viral", "#tiktok"]
        if "cenas" not in script or len(script["cenas"]) == 0:
            script["cenas"] = []

        # Garante que cada cena tem todos os campos
        for i, cena in enumerate(script["cenas"]):
            if "numero" not in cena:
                cena["numero"] = i + 1
            if "texto" not in cena:
                cena["texto"] = f"Parte {i + 1}"
            if "duracao" not in cena:
                cena["duracao"] = duration // max(len(script["cenas"]), 1)
            if "descricao_visual" not in cena:
                cena["descricao_visual"] = f"{theme_config['image_style']}, cinematic, 4k"
            if "emocao" not in cena:
                cena["emocao"] = "curiosidade"

            # Enriquece o prompt visual com o estilo do tema
            if theme_config["image_style"] not in cena["descricao_visual"]:
                cena["descricao_visual"] += f", {theme_config['image_style']}"
            cena["descricao_visual"] += ", vertical composition, 9:16 aspect ratio, ultra detailed"

        return script
