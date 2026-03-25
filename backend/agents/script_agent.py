"""
Agent 3: Script Generation — Creashort style
Duration-aware: forces correct word count so audio matches target duration.
"""
import json
import logging
from backend.utils.ai_client import chat_completion

logger = logging.getLogger(__name__)

# edge-tts at +15% speed = ~2.5 words/sec
WORDS_PER_SEC = 2.5


class ScriptGenerationAgent:
    SYSTEM = """You are an elite viral short-form video scriptwriter.
Your scripts have generated millions of views on TikTok, Reels and Shorts.

STRICT RULES:
1. Hook: first sentence MAX 10 words — must create instant curiosity or shock
2. Every sentence MAX 12 words — short = fast = high retention
3. NEVER start with "In this video", "Today", "Welcome", "Hey guys"
4. Speak directly: always use "you", "your"
5. No filler words, no padding, every word earns its place
6. full_script must be EXACTLY the word count requested
7. Image prompts: MAX 8 WORDS each, specific visual scenes

Respond ONLY in valid JSON. No markdown, no explanation."""

    async def generate(self, strategy: dict, job_id: str = "") -> dict:
        niche      = strategy.get("niche", "")
        target_sec = int(strategy.get("target_duration_sec", 30))
        # Calculate exact words needed
        target_words = int(target_sec * WORDS_PER_SEC)

        logger.info(f"[{job_id}] Script: '{strategy.get('topic','?')}' | {target_sec}s = {target_words} words")

        prompt = f"""
Niche: {niche}
Topic: {strategy.get('topic', '')}
Hook: {strategy.get('hook', '')}
Emotion: {strategy.get('emotion', 'curiosity')}
Target duration: {target_sec} seconds
REQUIRED word count: EXACTLY {target_words} words in full_script

Write a viral TikTok script. Hook in 3 seconds, deliver fast, end with CTA.

Return this JSON:
{{
  "title": "punchy internal title",
  "niche": "{niche}",
  "hook": {{
    "text": "first spoken sentence — max 10 words, stops the scroll",
    "technique": "shocking_stat|bold_claim|curiosity_gap|fear|contrarian"
  }},
  "body": [
    {{"text": "sentence 1 — max 12 words", "duration_sec": 4, "visual_note": "3-word scene description"}},
    {{"text": "sentence 2 — max 12 words", "duration_sec": 4, "visual_note": "3-word scene description"}},
    {{"text": "sentence 3 — max 12 words", "duration_sec": 4, "visual_note": "3-word scene description"}},
    {{"text": "sentence 4 — max 12 words", "duration_sec": 4, "visual_note": "3-word scene description"}},
    {{"text": "sentence 5 — max 12 words", "duration_sec": 4, "visual_note": "3-word scene description"}}
  ],
  "cta": {{
    "text": "specific call to action — not generic 'follow for more'",
    "type": "follow|comment|save|share"
  }},
  "full_script": "COMPLETE script as ONE flowing text block — MUST BE {target_words} WORDS",
  "target_duration_sec": {target_sec},
  "word_count": {target_words},
  "tone": "energetic|urgent|mysterious|inspiring|shocking",
  "image_prompts": [
    {{"prompt": "specific 5-7 word visual scene", "mood": "dramatic"}},
    {{"prompt": "specific 5-7 word visual scene", "mood": "intense"}},
    {{"prompt": "specific 5-7 word visual scene", "mood": "cinematic"}},
    {{"prompt": "specific 5-7 word visual scene", "mood": "epic"}}
  ]
}}

IMPORTANT: full_script must contain EXACTLY {target_words} words.
Count carefully. Pad with natural sentences if needed.
"""
        raw    = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.75)
        script = json.loads(raw)

        # Validate and fix word count if needed
        full   = script.get("full_script", "")
        actual = len(full.split())
        logger.info(f"[{job_id}] Script returned: {actual} words (target: {target_words})")

        # If script is way too short, expand it
        if actual < target_words * 0.6:
            logger.warning(f"[{job_id}] Script too short ({actual} words), expanding...")
            script = await self._expand_script(script, target_words, niche, job_id)

        return script

    async def _expand_script(self, script: dict, target_words: int, niche: str, job_id: str) -> dict:
        """Ask the LLM to expand a short script to the correct length."""
        current = script.get("full_script", "")
        prompt = f"""
This script is too short for the video:
"{current}"

Niche: {niche}
Required: EXACTLY {target_words} words.

Expand it naturally. Keep the same topic, hook and CTA.
Add more details, examples, or facts to reach {target_words} words.
Keep sentences short (max 12 words each).

Return JSON:
{{
  "full_script": "expanded script with exactly {target_words} words",
  "word_count": {target_words}
}}
"""
        raw = await chat_completion(
            "Expand this script to the exact word count. Return only JSON.",
            prompt, json_mode=True, temperature=0.7
        )
        expanded = json.loads(raw)
        script["full_script"] = expanded.get("full_script", current)
        script["word_count"]  = len(script["full_script"].split())
        logger.info(f"[{job_id}] Expanded to {script['word_count']} words")
        return script
