"""
Agent 2: Content Strategy — Creashort style
Define a estrutura exata do vídeo cena a cena.
"""
import json, logging
from backend.utils.ai_client import chat_completion
logger = logging.getLogger(__name__)

class ContentStrategyAgent:
    SYSTEM = """You are a short-form video director who produces viral faceless content.
You think in SCENES, not paragraphs. Every second counts.

Your videos follow this proven structure:
- 0-3s: HOOK — pattern interrupt, stop the scroll
- 3-8s: AMPLIFY — make the problem/promise bigger
- 8-25s: DELIVER — fast, punchy content delivery  
- 25-30s: CTA — natural, not salesy

You know that:
- Jump cuts every 2-3 seconds increase retention by 40%
- Text on screen + voiceover = 2x retention vs voiceover alone
- Dark/dramatic visuals outperform bright stock in most niches
- First 0.5 seconds determines if they swipe or stay

Respond ONLY in valid JSON."""

    async def generate(self, trends: dict, count: int = 1, job_id: str = "") -> list:
        logger.info(f"[{job_id}] Building {count} video strategies")
        best = trends.get("topics", [{}])
        prompt = f"""
Niche: "{trends.get('niche', '')}"
Best ideas: {json.dumps(best[:3], indent=2)}

Create EXACTLY {count} video structure(s). Each must feel like Creashort output.

Return JSON: {{"strategies": [
  {{
    "index": 0,
    "niche": "{trends.get('niche', '')}",
    "topic": "specific punchy topic",
    "hook": "exact first sentence — max 10 words, pattern interrupt",
    "hook_type": "shocking_stat|forbidden_knowledge|contrarian|fear|curiosity_gap",
    "angle": "unique angle that makes this different from generic content",
    "emotion": "primary emotion to trigger",
    "visual_style": "dark_cinematic|bright_high_energy|minimalist|dramatic_close_ups",
    "scenes": [
      {{
        "second": "0-3",
        "type": "hook",
        "voiceover": "exact words spoken",
        "visual": "5-word visual description for AI image",
        "text_overlay": "2-3 WORD SCREEN TEXT",
        "cut_type": "hard_cut|zoom_in|zoom_out|fade"
      }}
    ],
    "cta": "natural call to action last 3 seconds",
    "target_duration_sec": 30,
    "retention_hook": "what keeps viewer watching to the end"
  }}
]}}

Scenes: 6-10 scenes total covering the full video. Every scene has a purpose.
"""
        raw = await chat_completion(self.SYSTEM, prompt, json_mode=True, temperature=0.8)
        data = json.loads(raw)
        strategies = data.get("strategies", [])
        if not strategies and isinstance(data, list):
            strategies = data
        logger.info(f"[{job_id}] Strategies: {len(strategies)}")
        return strategies[:count]
