"""
Agent 4: Visual Agent
Pollinations.ai — grátis, sem chave, AI images.
Usa prompts curtos para melhor resultado e menor timeout.
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

        if not prompts:
            prompts = [{"prompt": niche} for _ in range(4)]

        logger.info(f"[{job_id}] {len(prompts)} images via '{image_source}'")

        results = []
        for idx, ip in enumerate(prompts):
            path = await self._get_one(ip, idx, job_id, image_source, niche)
            results.append(path)

        valid = [r for r in results if r and os.path.exists(r)]
        if not valid:
            raise RuntimeError(f"[{job_id}] All images failed")

        logger.info(f"[{job_id}] {len(valid)}/{len(prompts)} images OK")
        return valid

    async def _get_one(self, ip: dict, idx: int, job_id: str, source: str, niche: str) -> str:
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"img_{idx:02d}_{uuid.uuid4().hex[:6]}.jpg")

        # Build short prompt (max 80 chars) — Pollinations works much better
        raw_prompt = ip.get("prompt", ip.get("search_query", niche))
        short_prompt = self._shorten(raw_prompt, niche)

        if source == "pexels" and settings.has_pexels:
            try:
                p = await self._pexels(ip.get("search_query", niche), out_path, idx)
                if p:
                    logger.info(f"[{job_id}] img_{idx}: Pexels ✓")
                    return p
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx} Pexels: {e}")

        elif source == "dalle" and settings.OPENAI_API_KEY:
            try:
                p = await self._dalle(short_prompt, out_path.replace(".jpg", ".png"))
                logger.info(f"[{job_id}] img_{idx}: DALL·E ✓")
                return p
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx} DALL·E: {e}")

        elif source == "mixed":
            if idx == 0 and settings.has_pexels:
                try:
                    p = await self._pexels(ip.get("search_query", niche), out_path, idx)
                    if p:
                        return p
                except Exception:
                    pass

        # Pollinations (default + fallback)
        for attempt in range(3):
            try:
                p = await self._pollinations(short_prompt, out_path, seed=idx * 13 + attempt)
                logger.info(f"[{job_id}] img_{idx}: Pollinations ✓ (attempt {attempt+1})")
                return p
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx} Pollinations #{attempt+1}: {e}")
                if attempt < 2:
                    await asyncio.sleep(5)

        # Absolute last resort
        return await self._solid_color(out_path, idx)

    def _shorten(self, prompt: str, niche: str) -> str:
        """Extract a clean short prompt for Pollinations (max ~80 chars)."""
        # Remove style instructions already added globally
        clean = re.sub(r'(no text|no watermark|no logo|cinematic lighting|ultra sharp'
                       r'|vertical portrait|9:16|professional quality|vivid colors)', 
                       '', prompt, flags=re.IGNORECASE)
        clean = re.sub(r'\s+', ' ', clean).strip().rstrip(',.')
        # Keep first 80 chars
        if len(clean) > 80:
            clean = clean[:77] + "..."
        return clean if clean else niche

    async def _pollinations(self, prompt: str, out_path: str, seed: int = 0) -> str:
        # Style appended separately — short and effective
        full = f"{prompt}, cinematic, sharp, vivid"
        encoded = urllib.parse.quote(full)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=576&height=1024&seed={seed}&nologo=true&model=flux"
        )
        logger.debug(f"Pollinations URL: {url[:100]}...")

        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "image" not in ct:
                raise RuntimeError(f"Not image ({ct[:30]})")
            if len(resp.content) < 3000:
                raise RuntimeError(f"Too small: {len(resp.content)}B")
            with open(out_path, "wb") as f:
                f.write(resp.content)
        return out_path

    async def _pexels(self, query: str, out_path: str, idx: int) -> str | None:
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": settings.PEXELS_API_KEY},
                params={"query": query, "per_page": 10, "orientation": "portrait"},
            )
            r.raise_for_status()
            photos = r.json().get("photos", [])
            if not photos:
                return None
            img_url = photos[idx % len(photos)]["src"]["large"]
            img = await http.get(img_url, timeout=30)
            img.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(img.content)
        return out_path

    async def _dalle(self, prompt: str, out_path: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.images.generate(
            model="dall-e-3", prompt=prompt[:4000],
            size="1024x1792", quality="standard", n=1,
        )
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(resp.data[0].url)
            with open(out_path, "wb") as f:
                f.write(r.content)
        return out_path

    async def _solid_color(self, out_path: str, idx: int) -> str:
        colors = ["1a1a2e", "16213e", "0f3460", "533483", "2d132c"]
        c = colors[idx % len(colors)]
        png = out_path.replace(".jpg", ".png")
        cmd = ["ffmpeg", "-y", "-f", "lavfi",
               "-i", f"color=c=#{c}:size=576x1024:rate=1",
               "-frames:v", "1", png]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.communicate()
        logger.warning(f"img_{idx}: solid color fallback")
        return png
