"""
Agent 7: SEO & Caption — Creashort style
Títulos virais, captions que convertem, hashtags estratégicos.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

class SEOAgent:
    SYSTEM = """You are a TikTok/Reels/Shorts growth expert who has grown accounts to millions.
You write captions that feel native to the platform — never corporate.

Caption formula that works:
- Line 1: Mirror the hook (creates continuity)
- Line 2: Add context or tease the reveal  
- Line 3: CTA that feels organic

Hashtag strategy:
- 2-3 niche-specific (small: 100k-1M views)
- 2-3 medium (1M-10M)
- 2 broad (#fyp #foryou)
Never use irrelevant trending hashtags.

Respond ONLY in valid JSON."""

    async def generate(self, strategy: dict, script: dict, job_id: str = "") -> dict:
        logger.info(f"[{job_id}] SEO: {strategy.get('topic', '?')}")
        hook = script.get("hook", {}).get("text", "")
        niche = strategy.get("niche", "")
        tone = script.get("tone", "energetic")

        prompt = f"""
Niche: {niche}
Hook: "{hook}"
Topic: {strategy.get('topic', '')}
Tone: {tone}
Full script preview: "{script.get('full_script', '')[:200]}"

Create viral SEO package. Return JSON:
{{
  "title": "main video title — punchy, max 60 chars, no clickbait",
  "alt_titles": [
    "alternative title 2",
    "alternative title 3"
  ],
  "caption": "TikTok caption — 1-2 lines, conversational, 1 emoji max",
  "hashtags": ["#specific1", "#specific2", "#niche1", "#niche2", "#fyp", "#foryou", "#viral"],
  "ready_to_post_text": "caption\\n\\n#hashtag1 #hashtag2 #hashtag3 #fyp #foryou",
  "seo_keywords": ["keyword1", "keyword2", "keyword3"],
  "best_time_to_post": "e.g. Tuesday 7-9pm EST",
  "engagement_tip": "specific tip for this exact video to maximize comments"
}}
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.7)
        result = json.loads(raw)
        logger.info(f"[{job_id}] Title: \"{result.get('title', '')[:50]}\"")
        return result
