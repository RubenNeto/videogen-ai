"""
Cliente AI universal — suporta Groq, Gemini e OpenAI.
Os agentes chamam sempre chat_completion() sem saber qual provider está a ser usado.

GROQ:   API compatível com OpenAI, usa endpoint diferente
GEMINI: Google AI, tem endpoint próprio mas retorna texto limpo
OPENAI: API original

Prioridade automática: Groq > Gemini > OpenAI
"""
import json
import logging
import httpx
from backend.utils.config import settings

logger = logging.getLogger(__name__)


async def chat_completion(
    system: str,
    user: str,
    json_mode: bool = True,
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> str:
    """
    Chama o provider AI disponível e retorna a resposta como string.
    Se json_mode=True, a resposta é JSON válido.
    """
    provider = settings.ai_provider

    if provider == "groq":
        return await _groq(system, user, json_mode, temperature, max_tokens)
    elif provider == "gemini":
        return await _gemini(system, user, json_mode, temperature, max_tokens)
    elif provider == "openai":
        return await _openai(system, user, json_mode, temperature, max_tokens)
    else:
        raise RuntimeError(
            "Nenhuma chave AI configurada.\n"
            "Adiciona ao .env uma das seguintes (todas grátis):\n"
            "  GROQ_API_KEY=gsk_...   (https://console.groq.com)\n"
            "  GEMINI_API_KEY=AIza... (https://aistudio.google.com)\n"
            "  OPENAI_API_KEY=sk-...  (https://platform.openai.com)"
        )


# ── GROQ ─────────────────────────────────────────────────────────────────────
# API 100% compatível com OpenAI — ultra rápido, grátis
async def _groq(system, user, json_mode, temperature, max_tokens) -> str:
    async with httpx.AsyncClient(timeout=60) as http:
        payload = {
            "model": settings.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        resp = await http.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        logger.debug(f"Groq response: {content[:100]}...")
        return content


# ── GEMINI ────────────────────────────────────────────────────────────────────
# Google AI Studio — grátis com limites generosos
async def _gemini(system, user, json_mode, temperature, max_tokens) -> str:
    async with httpx.AsyncClient(timeout=60) as http:
        prompt = f"{system}\n\n{user}"
        if json_mode:
            prompt += "\n\nResponde APENAS com JSON válido, sem texto adicional, sem ```json."

        resp = await http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent",
            params={"key": settings.GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]

        # Limpar markdown se necessário
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        logger.debug(f"Gemini response: {content[:100]}...")
        return content.strip()


# ── OPENAI ────────────────────────────────────────────────────────────────────
async def _openai(system, user, json_mode, temperature, max_tokens) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    kwargs = {
        "model": settings.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = await client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content
    logger.debug(f"OpenAI response: {content[:100]}...")
    return content


def get_provider_name() -> str:
    """Retorna nome legível do provider ativo."""
    names = {
        "groq":   f"Groq ({settings.GROQ_MODEL})",
        "gemini": f"Gemini ({settings.GEMINI_MODEL})",
        "openai": f"OpenAI ({settings.OPENAI_MODEL})",
        "none":   "Nenhum configurado",
    }
    return names[settings.ai_provider]
