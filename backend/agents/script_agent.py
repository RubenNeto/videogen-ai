"""
Agent 3: Script Generation — uses Groq, Gemini or OpenAI.
Respects target_duration_sec from strategy.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

# Approximate words per second for normal speech (after +15% speed)
WORDS_PER_SEC = 2.8

class ScriptGenerationAgent:
    SYSTEM = """You are an elite TikTok scriptwriter for US audiences.
Rules you never break:
1. Hook in FIRST 3 SECONDS — pattern interrupt or curiosity gap
2. Every sentence earns the next — zero filler
3. Conversational US English — like texting a friend
4. End with a natural CTA that does not feel salesy
5. Script works as pure voiceover narration
Respond ONLY in valid JSON."""

    async def generate(self, strategy: dict, job_id: str = "") -> dict:
        logger.info(f"[{job_id}] Writing script for: {strategy.get('topic', '?')}")
        niche = strategy.get("niche", "")
        target_sec = int(strategy.get("target_duration_sec", 30))
        # Calculate target word count based on speed (2.8 words/sec after +15% speedup)
        target_words = int(target_sec * WORDS_PER_SEC)

        prompt = f"""
Strategy:
{json.dumps(strategy, indent=2)}

IMPORTANT: Target duration is EXACTLY {target_sec} seconds.
Write approximately {target_words} words total (at 2.8 words/second spoken pace).

Return JSON:
{{
  "title": "internal title",
  "niche": "{niche}",
  "hook": {{
    "text": "exact words for first 3 seconds — max 8 words",
    "technique": "curiosity_gap|shocking_stat|bold_claim|relatable_scenario"
  }},
  "body": [
    {{
      "text": "narration for this segment",
      "duration_sec": 5,
      "visual_note": "brief description for image"
    }}
  ],
  "cta": {{
    "text": "natural CTA last 3 seconds",
    "type": "follow|comment|save|share"
  }},
  "full_script": "complete script as single flowing text",
  "target_duration_sec": {target_sec},
  "word_count": {target_words},
  "tone": "energetic|calm|urgent|funny|inspiring|serious",
  "image_prompts": [
    {{
      "prompt": "vivid AI image description, dramatic lighting, cinematic, {niche} theme",
      "mood": "visual mood"
    }},
    {{
      "prompt": "vivid AI image description, dramatic lighting, cinematic, {niche} theme",
      "mood": "visual mood"
    }},
    {{
      "prompt": "vivid AI image description, dramatic lighting, cinematic, {niche} theme",
      "mood": "visual mood"
    }},
    {{
      "prompt": "vivid AI image description, dramatic lighting, cinematic, {niche} theme",
      "mood": "visual mood"
    }}
  ]
}}

Critical: full_script must be approximately {target_words} words.
Image prompts should be vivid and cinematic — no text, no logos, no watermarks.
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.75)
        script = json.loads(raw)
        logger.info(f"[{job_id}] Script: {script.get('word_count',0)} words, target={target_sec}s")
        return script
