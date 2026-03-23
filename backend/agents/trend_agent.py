"""
Agent 1: Trend & Ideas — Creashort style
Gera 3 ideias virais com hook psicológico forte + análise de padrões.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

class TrendAnalysisAgent:
    SYSTEM = """You are a viral short-form video strategist who has studied every viral video
on TikTok, Reels and Shorts. You know exactly what makes people stop scrolling.

You understand:
- Pattern interrupts that stop the scroll in frame 1
- Curiosity gaps that force watch completion
- Emotional triggers (fear, greed, envy, awe, shock)
- The "forbidden knowledge" format that gets 10x shares
- Why faceless videos outperform face-reveal in certain niches

Respond ONLY in valid JSON."""

    async def analyze(self, niche: str, job_id: str = "") -> dict:
        logger.info(f"[{job_id}] Trend analysis: {niche}")
        prompt = f"""
Niche: "{niche}"

Generate 3 viral video ideas for this niche. Think like Creashort.ai — scroll-stopping, 
high retention, faceless format.

Return this EXACT JSON:
{{
  "niche": "{niche}",
  "topics": [
    {{
      "title": "specific punchy video title",
      "hook": "exact scroll-stopping first sentence (max 10 words, creates FOMO or shock)",
      "hook_type": "shocking_stat|forbidden_knowledge|contrarian|fear|curiosity_gap|transformation",
      "why_viral": "psychological reason this spreads",
      "emotion": "fear|greed|awe|anger|envy|inspiration",
      "retention_trick": "specific technique to keep viewers watching",
      "visual_style": "dark_cinematic|bright_energetic|minimalist|dramatic|educational",
      "score": 9
    }}
  ],
  "hashtags": {{
    "niche": ["#tag1", "#tag2", "#tag3"],
    "broad": ["#fyp", "#foryou", "#viral"]
  }},
  "best_posting_time": "describe optimal posting window",
  "hook_templates": [
    "Nobody tells you this about [TOPIC]...",
    "I tested [TOPIC] for 30 days. The result?",
    "This [TOPIC] secret changed everything."
  ]
}}

Make all 3 ideas genuinely different formats. All in ENGLISH. Be specific, not generic.
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.85)
        result = json.loads(raw)
        logger.info(f"[{job_id}] Ideas: {[t['title'] for t in result.get('topics', [])]}")
        return result
