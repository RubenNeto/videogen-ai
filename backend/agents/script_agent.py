"""
Agent 3: Script Generation — funciona com Groq, Gemini ou OpenAI.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

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
        prompt = f"""
Strategy:
{json.dumps(strategy, indent=2)}

Write a complete TikTok voiceover script. Target duration: 20-35 seconds.

Return JSON:
{{
  "title": "internal title",
  "niche": "{niche}",
  "hook": {{
    "text": "exact words for first 3 seconds only",
    "technique": "curiosity_gap|shocking_stat|bold_claim|relatable_scenario"
  }},
  "body": [
    {{
      "text": "narration for this segment",
      "duration_sec": 5,
      "visual_note": "brief description for image search"
    }}
  ],
  "cta": {{
    "text": "natural CTA for last 3 seconds",
    "type": "follow|comment|save|share"
  }},
  "full_script": "complete script as single flowing text",
  "target_duration_sec": 30,
  "word_count": 75,
  "tone": "energetic|calm|urgent|funny|inspiring|serious",
  "image_prompts": [
    {{
      "prompt": "detailed photorealistic description for scene 1",
      "search_query": "specific 2-3 word Pexels query e.g. mustang gt500 red",
      "mood": "visual mood"
    }},
    {{
      "prompt": "detailed description for scene 2",
      "search_query": "specific Pexels query",
      "mood": "visual mood"
    }},
    {{
      "prompt": "detailed description for scene 3",
      "search_query": "specific Pexels query",
      "mood": "visual mood"
    }},
    {{
      "prompt": "detailed description for scene 4",
      "search_query": "specific Pexels query",
      "mood": "visual mood"
    }}
  ]
}}

Body: 3-5 segments. Total: 60-120 words. Image search_query must be niche-specific.
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.75)
        script = json.loads(raw)
        logger.info(f"[{job_id}] Script hook: \"{script.get('hook', {}).get('text', '')[:50]}...\"")
        return script
