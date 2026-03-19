"""
Agent 4: Visual Agent
Usa Pollinations.ai — 100% grátis, sem API key, imagens AI geradas.
Fallback: cor sólida via FFmpeg.
"""
import asyncio
import logging
import os
import uuid
import urllib.parse
import httpx
from backend.utils.config import settings

logger = logging.getLogger(__name__)

# Pollinations.ai — API pública gratuita, sem registo
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"


class VisualAgent:

    STYLE_SUFFIX = (
        "cinematic, vertical 9:16 portrait, "
        "sharp focus, professional photography, "
        "vivid colors, no text, no watermark"
    )

    async def generate(self, script: dict, job_id: str = "") -> list[str]:
        image_prompts = script.get("image_prompts", [])
        niche = script.get("niche", "")

        if not image_prompts:
            image_prompts = [
                {"prompt": seg.get("visual_note", niche), "search_query": niche}
                for seg in script.get("body", [{"visual_note": niche}])
            ]

        logger.info(f"[{job_id}] Generating {len(image_prompts)} AI images via Pollinations")

        results = []
        for idx, ip in enumerate(image_prompts):
            try:
                r = await self._get_image(ip, idx, job_id)
                results.append(r)
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx} failed: {e}")
                results.append(e)

        valid = [r for r in results if isinstance(r, str) and os.path.exists(r)]
        if not valid:
            raise RuntimeError(f"[{job_id}] All image generation attempts failed")

        logger.info(f"[{job_id}] Got {len(valid)}/{len(image_prompts)} images")
        return valid

    async def _get_image(self, image_prompt: dict, idx: int, job_id: str) -> str:
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"img_{idx:02d}_{uuid.uuid4().hex[:6]}.jpg")

        ai_prompt = image_prompt.get("prompt", image_prompt.get("search_query", "abstract"))

        # 1. Pollinations.ai (grátis, sem key)
        try:
            path = await self._pollinations(ai_prompt, out_path, idx)
            logger.info(f"[{job_id}] img_{idx}: Pollinations ✓")
            return path
        except Exception as e:
            logger.warning(f"[{job_id}] img_{idx}: Pollinations failed: {e}")

        # 2. DALL·E (se tiver OpenAI key)
        if settings.OPENAI_API_KEY:
            try:
                path = await self._dalle(ai_prompt, out_path.replace(".jpg", ".png"))
                logger.info(f"[{job_id}] img_{idx}: DALL·E ✓")
                return path
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx}: DALL·E failed: {e}")

        # 3. Último recurso — cor sólida
        return await self._color_fallback(out_path, idx)

    async def _pollinations(self, prompt: str, out_path: str, seed: int) -> str:
        """
        Pollinations.ai — API gratuita, sem registo, sem limites.
        https://pollinations.ai
        """
        full_prompt = f"{prompt}, {self.STYLE_SUFFIX}"
        encoded = urllib.parse.quote(full_prompt)

        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1080&height=1920"
            f"&seed={seed}"
            f"&nologo=true"
            f"&enhance=true"
        )

        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
            resp = await http.get(url)
            resp.raise_for_status()

            # Verificar que é mesmo uma imagem
            ct = resp.headers.get("content-type", "")
            if "image" not in ct and len(resp.content) < 1000:
                raise RuntimeError(f"Not an image response: {ct}")

            with open(out_path, "wb") as f:
                f.write(resp.content)

        return out_path

    async def _dalle(self, prompt: str, out_path: str) -> str:
        from openai import AsyncOpenAI
        import httpx as _httpx
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.images.generate(
            model="dall-e-3",
            prompt=f"{prompt}. {self.STYLE_SUFFIX}"[:4000],
            size="1024x1792",
            quality="standard",
            n=1,
        )
        img_url = resp.data[0].url
        async with _httpx.AsyncClient(timeout=30) as http:
            img_resp = await http.get(img_url)
            with open(out_path, "wb") as f:
                f.write(img_resp.content)
        return out_path

    async def _color_fallback(self, out_path: str, idx: int) -> str:
        colors = ["#1a1a2e", "#16213e", "#0f3460", "#533483", "#2d132c"]
        color = colors[idx % len(colors)]
        png_path = out_path.replace(".jpg", ".png")
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c={color}:size=1080x1920:rate=1",
            "-frames:v", "1", png_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        logger.warning(f"Using color fallback for image {idx}")
        return png_path
