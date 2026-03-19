"""
Agent 1: Trend Analysis — funciona com Groq, Gemini ou OpenAI.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

class TrendAnalysisAgent:
    SYSTEM = """You are a TikTok viral content analyst. Analyze the given niche and return
data-driven insights about what content performs best for US English audiences.
Focus on: emotional triggers, hook patterns, high-retention formats.
Respond ONLY in valid JSON."""

    async def analyze(self, niche: str, job_id: str = "") -> dict:
        logger.info(f"[{job_id}] Analyzing trends for: {niche}")
        prompt = f"""
Niche: "{niche}"

Return JSON with this EXACT structure:
{{
  "niche": "{niche}",
  "topics": [
    {{
      "title": "specific video topic",
      "why_viral": "psychological reason",
      "emotion": "curiosity|fear|inspiration|humor|shock|relatability",
      "format": "storytime|tutorial|listicle|myth_busting|POV|challenge|reaction",
      "hook_idea": "exact words for first 3 seconds",
      "potential": "high|very_high"
    }}
  ],
  "hashtags": {{
    "broad": ["#tag1", "#tag2"],
    "niche": ["#tag3", "#tag4"],
    "trending": ["#fyp", "#foryoupage", "#viral"]
  }},
  "hook_templates": ["Template 1", "Template 2", "Template 3"],
  "avoid": ["thing to avoid 1", "thing to avoid 2"],
  "optimal_length": "20-35 seconds"
}}

Generate exactly 5 topics. All content in ENGLISH for US audience.
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.7)
        result = json.loads(raw)
        logger.info(f"[{job_id}] Topics: {[t['title'] for t in result.get('topics', [])]}")
        return result
