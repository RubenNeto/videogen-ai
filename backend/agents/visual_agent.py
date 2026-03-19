"""
Agent 4: Visual Agent
Usa Pollinations.ai — 100% grátis, sem API key, imagens AI geradas.
Aumentado timeout para 90s (Pollinations pode ser lento).
"""
import asyncio
import logging
import os
import uuid
import urllib.parse
import httpx
from backend.utils.config import settings

logger = logging.getLogger(__name__)


class VisualAgent:

    STYLE = (
        "cinematic dramatic lighting, vertical portrait 9:16, "
        "ultra sharp, professional quality, vivid colors, "
        "no text, no watermark, no logo"
    )

    async def generate(self, script: dict, job_id: str = "") -> list[str]:
        image_prompts = script.get("image_prompts", [])
        niche = script.get("niche", "")

        if not image_prompts:
            image_prompts = [
                {"prompt": seg.get("visual_note", niche)}
                for seg in script.get("body", [{"visual_note": niche}])
            ]

        logger.info(f"[{job_id}] Generating {len(image_prompts)} AI images via Pollinations")

        results = []
        for idx, ip in enumerate(image_prompts):
            path = await self._get_image(ip, idx, job_id)
            results.append(path)

        valid = [r for r in results if r and os.path.exists(r)]
        if not valid:
            raise RuntimeError(f"[{job_id}] All image generation failed")

        logger.info(f"[{job_id}] Got {len(valid)}/{len(image_prompts)} images")
        return valid

    async def _get_image(self, image_prompt: dict, idx: int, job_id: str) -> str:
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"img_{idx:02d}_{uuid.uuid4().hex[:6]}.jpg")

        prompt = image_prompt.get("prompt", "abstract cinematic scene")

        # Try Pollinations with retry
        for attempt in range(3):
            try:
                path = await self._pollinations(prompt, out_path, seed=idx + attempt * 10)
                logger.info(f"[{job_id}] img_{idx}: Pollinations ✓")
                return path
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx} attempt {attempt+1}: {e}")
                if attempt < 2:
                    await asyncio.sleep(3)

        # DALL·E fallback
        if settings.OPENAI_API_KEY:
            try:
                path = await self._dalle(prompt, out_path.replace(".jpg", ".png"))
                logger.info(f"[{job_id}] img_{idx}: DALL·E ✓")
                return path
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx}: DALL·E failed: {e}")

        # Color fallback — never leave video imageless
        logger.warning(f"[{job_id}] img_{idx}: using color fallback")
        return await self._color_fallback(out_path, idx)

    async def _pollinations(self, prompt: str, out_path: str, seed: int = 0) -> str:
        full = f"{prompt}, {self.STYLE}"
        encoded = urllib.parse.quote(full)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1080&height=1920&seed={seed}&nologo=true&enhance=true&model=flux"
        )

        # 90s timeout — Pollinations can be slow
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as http:
            resp = await http.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                raise RuntimeError(f"Not an image: {content_type[:50]}")
            if len(resp.content) < 5000:
                raise RuntimeError(f"Image too small ({len(resp.content)} bytes)")

            with open(out_path, "wb") as f:
                f.write(resp.content)

        return out_path

    async def _dalle(self, prompt: str, out_path: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.images.generate(
            model="dall-e-3",
            prompt=f"{prompt}. {self.STYLE}"[:4000],
            size="1024x1792",
            quality="standard", n=1,
        )
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(resp.data[0].url)
            with open(out_path, "wb") as f:
                f.write(r.content)
        return out_path

    async def _color_fallback(self, out_path: str, idx: int) -> str:
        colors = ["0f0c29", "302b63", "24243e", "0f2027", "1a1a2e"]
        c = colors[idx % len(colors)]
        png = out_path.replace(".jpg", ".png")
        cmd = ["ffmpeg", "-y", "-f", "lavfi",
               "-i", f"color=c=#{c}:size=1080x1920:rate=1",
               "-frames:v", "1", png]
        proc = await asyncio.create_subprocess_exec(*cmd,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.communicate()
        return png
