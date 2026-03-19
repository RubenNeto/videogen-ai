"""
Agent 7: SEO & Caption — funciona com Groq, Gemini ou OpenAI.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

class SEOAgent:
    SYSTEM = """You are a TikTok SEO and caption expert.
Write captions that feel authentic, drive engagement, and maximise reach.
Respond ONLY in valid JSON."""

    async def generate(self, strategy: dict, script: dict, job_id: str = "") -> dict:
        logger.info(f"[{job_id}] Generating SEO for: {strategy.get('topic', '?')}") 
        prompt = f"""
Strategy: {json.dumps(strategy, indent=2)}
Hook: "{script.get('hook', {}).get('text', '')}"
Tone: "{script.get('tone', 'energetic')}"

Return JSON:
{{
  "title": "video title max 80 chars, compelling not clickbait",
  "caption": "TikTok caption 120-180 chars, conversational, 1-2 emojis",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5", "#fyp", "#foryou"],
  "ready_to_post_text": "full text to paste into TikTok — caption + newline + hashtags",
  "engagement_tip": "one specific tip to boost engagement for this video"
}}

Rules: max 7 hashtags. Mix: 2 niche + 3 broad topic + #fyp + #foryou.
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.6)
        data = json.loads(raw)
        logger.info(f"[{job_id}] Caption: \"{data.get('title', '')[:50]}\"")
        return data
