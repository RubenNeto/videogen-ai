"""
Agent 4: Visual Agent
- Pollinations.ai — grátis, sem chave
- Prompts curtos e diretos (melhor qualidade, mais rápido)
- Timeout 120s com 2 tentativas
- Fallback: cor sólida (nunca deixa o vídeo sem imagens)
"""
import asyncio
import logging
import os
import re
import uuid
import urllib.parse
import httpx
from backend.utils.config import settings

logger = logging.getLogger(__name__)


class VisualAgent:

    async def generate(self, script: dict, job_id: str = "", image_source: str = "pollinations") -> list[str]:
        prompts = script.get("image_prompts", [])
        niche   = script.get("niche", "cinematic scene")

        # Ensure we have exactly 4 prompts
        if not prompts:
            prompts = [
                {"prompt": f"{niche} dramatic close-up"},
                {"prompt": f"{niche} wide cinematic shot"},
                {"prompt": f"{niche} action moment"},
                {"prompt": f"{niche} epic final scene"},
            ]
        elif len(prompts) < 4:
            while len(prompts) < 4:
                prompts.append({"prompt": f"{niche} cinematic scene"})

        logger.info(f"[{job_id}] Generating {len(prompts)} images | source={image_source}")

        results = []
        for idx, ip in enumerate(prompts[:4]):  # max 4 images
            path = await self._get_image(ip, idx, job_id, image_source, niche)
            results.append(path)

        valid = [r for r in results if r and os.path.exists(r)]
        if not valid:
            raise RuntimeError(f"[{job_id}] All images failed")

        logger.info(f"[{job_id}] {len(valid)}/{len(prompts)} images OK")
        return valid

    async def _get_image(self, ip: dict, idx: int, job_id: str, source: str, niche: str) -> str:
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"img_{idx:02d}_{uuid.uuid4().hex[:6]}.jpg")

        # Clean short prompt
        raw_prompt = ip.get("prompt", ip.get("search_query", niche))
        prompt     = self._clean_prompt(raw_prompt, niche)

        # Route by source
        if source == "pexels" and settings.has_pexels:
            p = await self._pexels(ip.get("search_query", niche), out_path, idx)
            if p:
                return p
            # fallthrough to Pollinations

        elif source == "dalle" and settings.OPENAI_API_KEY:
            try:
                return await self._dalle(prompt, out_path.replace(".jpg", ".png"))
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx} DALL·E: {e}")

        # Pollinations (default + fallback)
        for attempt in range(2):
            try:
                p = await self._pollinations(prompt, out_path, seed=idx * 17 + attempt)
                logger.info(f"[{job_id}] img_{idx}: Pollinations ✓ '{prompt[:40]}'")
                return p
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx} attempt {attempt+1}: {e}")
                if attempt == 0:
                    await asyncio.sleep(3)

        # Solid color fallback — ALWAYS produces a result
        logger.warning(f"[{job_id}] img_{idx}: using color fallback")
        return await self._color_fallback(out_path, idx)

    def _clean_prompt(self, prompt: str, niche: str) -> str:
        """Keep prompt short and clean for Pollinations."""
        # Remove style words we'll add ourselves
        clean = re.sub(
            r'(no text|no watermark|no logo|vertical|9:16|portrait|'
            r'ultra sharp|professional|high quality|photorealistic)',
            '', prompt, flags=re.IGNORECASE
        )
        clean = re.sub(r'\s+', ' ', clean).strip().strip(',.')
        # Truncate to 60 chars max
        if len(clean) > 60:
            clean = clean[:57] + "..."
        return clean or niche

    async def _pollinations(self, prompt: str, out_path: str, seed: int = 0) -> str:
        """
        Pollinations.ai — completely free, no API key.
        Uses flux model which is fastest and best quality.
        """
        full    = f"{prompt}, cinematic dramatic lighting, sharp"
        encoded = urllib.parse.quote(full)
        url     = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=576&height=1024&seed={seed}&nologo=true&model=flux&enhance=false"
        )
        logger.debug(f"Pollinations: {url[:80]}...")

        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
            resp = await http.get(url)
            resp.raise_for_status()

            ct = resp.headers.get("content-type", "")
            if "image" not in ct:
                raise RuntimeError(f"Not an image: {ct[:40]}")
            if len(resp.content) < 5000:
                raise RuntimeError(f"Image too small: {len(resp.content)}B")

            with open(out_path, "wb") as f:
                f.write(resp.content)

        return out_path

    async def _pexels(self, query: str, out_path: str, idx: int):
        try:
            async with httpx.AsyncClient(timeout=20) as http:
                r = await http.get(
                    "https://api.pexels.com/v1/search",
                    headers={"Authorization": settings.PEXELS_API_KEY},
                    params={"query": query, "per_page": 8, "orientation": "portrait"},
                )
                r.raise_for_status()
                photos = r.json().get("photos", [])
                if not photos:
                    return None
                url = photos[idx % len(photos)]["src"]["large"]
                img = await http.get(url, timeout=30)
                with open(out_path, "wb") as f:
                    f.write(img.content)
            return out_path
        except Exception as e:
            logger.warning(f"Pexels: {e}")
            return None

    async def _dalle(self, prompt: str, out_path: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp   = await client.images.generate(
            model="dall-e-3", prompt=prompt[:4000],
            size="1024x1792", quality="standard", n=1,
        )
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(resp.data[0].url)
            with open(out_path, "wb") as f:
                f.write(r.content)
        return out_path

    async def _color_fallback(self, out_path: str, idx: int) -> str:
        """Dark gradient fallback — always works."""
        # Use different dark gradient per image for variety
        gradients = [
            "color=c=#0f0c29:size=576x1024",
            "color=c=#1a1a2e:size=576x1024",
            "color=c=#16213e:size=576x1024",
            "color=c=#0f3460:size=576x1024",
        ]
        grad = gradients[idx % len(gradients)]
        png  = out_path.replace(".jpg", ".png")
        cmd  = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"{grad}:rate=1",
                "-frames:v", "1", png]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
        return png
