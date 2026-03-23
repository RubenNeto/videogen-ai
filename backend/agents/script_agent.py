"""
Agent 3: Script — Creashort style
Script otimizado para retenção máxima. Frases curtas. Ritmo rápido.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

WORDS_PER_SEC = 2.5  # slightly slower = clearer delivery

class ScriptGenerationAgent:
    SYSTEM = """You are the world's best viral short-form video scriptwriter.
Your scripts are used by creators with 10M+ followers.

Non-negotiable rules:
1. HOOK in first 3 seconds — MUST create instant curiosity or shock
2. Max 12 words per sentence — shorter = faster = better retention
3. NEVER say "In this video" or "Today we're talking about"
4. Use "you" — speak directly to the viewer
5. Create pattern interrupts every 5-8 seconds
6. End on a cliffhanger or strong CTA — never just "follow for more"
7. Write for SPOKEN delivery — no markdown, no punctuation except periods and commas

Creashort formula:
- Hook: Bold claim or shocking fact (0-3s)
- Problem/Promise: Amplify why this matters (3-8s)  
- Delivery: Fast punchy facts or story (8-25s)
- Twist/Reveal: Unexpected angle (20-28s)
- CTA: Specific action (28-30s)

Respond ONLY in valid JSON."""

    async def generate(self, strategy: dict, job_id: str = "") -> dict:
        logger.info(f"[{job_id}] Script: {strategy.get('topic', '?')}")
        niche = strategy.get("niche", "")
        target_sec = int(strategy.get("target_duration_sec", 30))
        target_words = int(target_sec * WORDS_PER_SEC)
        scenes = strategy.get("scenes", [])

        prompt = f"""
Strategy:
- Niche: {niche}
- Topic: {strategy.get('topic', '')}
- Hook: {strategy.get('hook', '')}
- Emotion: {strategy.get('emotion', 'curiosity')}
- Visual style: {strategy.get('visual_style', 'dark_cinematic')}
- Target: EXACTLY {target_sec} seconds = ~{target_words} words spoken

Scene structure:
{json.dumps(scenes, indent=2) if scenes else 'Create 6-8 scenes'}

Write the complete script. Every word must earn its place.

Return JSON:
{{
  "title": "internal reference title",
  "niche": "{niche}",
  "hook": {{
    "text": "exact first sentence — max 10 words, STOPS the scroll",
    "technique": "shocking_stat|bold_claim|curiosity_gap|fear|contrarian"
  }},
  "body": [
    {{
      "text": "sentence spoken in this scene — max 15 words",
      "duration_sec": 4,
      "visual_note": "5-word visual for this moment",
      "text_overlay": "2-3 WORD OVERLAY"
    }}
  ],
  "cta": {{
    "text": "specific CTA — not generic",
    "type": "follow|comment|save|share"
  }},
  "full_script": "complete script as single flowing text for TTS",
  "target_duration_sec": {target_sec},
  "word_count": {target_words},
  "tone": "energetic|urgent|mysterious|inspiring|shocking",
  "image_prompts": [
    {{
      "prompt": "red mustang burning rubber at night",
      "mood": "intense"
    }},
    {{
      "prompt": "close up engine roaring flames",
      "mood": "dramatic"
    }},
    {{
      "prompt": "highway speed blur neon lights",
      "mood": "fast"
    }},
    {{
      "prompt": "driver silhouette sunset mountains",
      "mood": "epic"
    }}
  ]
}}

CRITICAL:
- full_script = EXACTLY {target_words} words
- image_prompts = 4 prompts, each MAX 8 WORDS, very specific and visual
- No generic stock photo vibes — cinematic AI art style
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.8)
        script = json.loads(raw)
        logger.info(f"[{job_id}] Script: {script.get('word_count', 0)} words | hook: \"{script.get('hook', {}).get('text', '')[:40]}\"")
        return script
