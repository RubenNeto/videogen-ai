"""
Agent 2: Content Strategy — funciona com Groq, Gemini ou OpenAI.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

class ContentStrategyAgent:
    SYSTEM = """You are a viral short-form video strategist.
Create content plans that maximise watch time, saves, and follows.
Always ensure variation across multiple videos in the same batch.
Respond ONLY in valid JSON."""

    async def generate(self, trends: dict, count: int = 3, job_id: str = "") -> list:
        logger.info(f"[{job_id}] Generating {count} strategies")
        prompt = f"""
Trend data:
{json.dumps(trends, indent=2)}

Create EXACTLY {count} video strategies, each with a DIFFERENT format and emotional angle.

Return JSON: {{"strategies": [
  {{
    "index": 0,
    "niche": "{trends.get("niche", "")}",
    "topic": "specific topic",
    "format": "content format",
    "angle": "emotional angle",
    "hook_concept": "exact hook for first 3 seconds",
    "body_flow": "how the middle 15-25 seconds flows",
    "cta": "specific call to action text",
    "target_emotion": "primary emotion to trigger",
    "visual_theme": "description of visual style",
    "estimated_virality": "score 1-10"
  }}
]}}
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.8)
        data = json.loads(raw)
        strategies = data.get("strategies", [])
        if not strategies and isinstance(data, list):
            strategies = data
        logger.info(f"[{job_id}] Strategies: {[s.get('angle', '?') for s in strategies]}")
        return strategies[:count]
