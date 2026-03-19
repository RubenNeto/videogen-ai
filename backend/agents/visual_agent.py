"""
Agent 4: Visual Agent
Usa image_source para decidir de onde vêm as imagens:
  - pollinations : Pollinations.ai — grátis, sem chave, AI geradas (DEFAULT)
  - pexels       : Pexels — fotos reais, chave grátis
  - dalle        : DALL·E 3 — requer OPENAI_API_KEY
  - mixed        : primeira Pexels, restantes Pollinations
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
        "ultra sharp, vivid colors, professional quality, "
        "no text, no watermark, no logo"
    )

    async def generate(self, script: dict, job_id: str = "", image_source: str = "pollinations") -> list[str]:
        image_prompts = script.get("image_prompts", [])
        niche = script.get("niche", "")

        if not image_prompts:
            image_prompts = [
                {"prompt": seg.get("visual_note", niche), "search_query": niche}
                for seg in script.get("body", [{"visual_note": niche}])
            ]

        logger.info(f"[{job_id}] {len(image_prompts)} images via '{image_source}'")

        results = []
        for idx, ip in enumerate(image_prompts):
            path = await self._get_image(ip, idx, job_id, image_source)
            results.append(path)

        valid = [r for r in results if r and os.path.exists(r)]
        if not valid:
            raise RuntimeError(f"[{job_id}] All image generation failed")

        logger.info(f"[{job_id}] Got {len(valid)}/{len(image_prompts)} images")
        return valid

    async def _get_image(self, ip: dict, idx: int, job_id: str, image_source: str) -> str:
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"img_{idx:02d}_{uuid.uuid4().hex[:6]}.jpg")

        prompt       = ip.get("prompt", ip.get("search_query", "cinematic scene"))
        search_query = ip.get("search_query", prompt)

        # Route by image_source
        if image_source == "pexels" and settings.has_pexels:
            try:
                p = await self._pexels(search_query, out_path, idx)
                if p:
                    logger.info(f"[{job_id}] img_{idx}: Pexels ✓")
                    return p
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx}: Pexels failed: {e}")
            # Fallback to Pollinations if Pexels fails
            return await self._pollinations_with_retry(prompt, out_path, idx, job_id)

        elif image_source == "dalle" and settings.OPENAI_API_KEY:
            try:
                p = await self._dalle(prompt, out_path.replace(".jpg", ".png"))
                logger.info(f"[{job_id}] img_{idx}: DALL·E ✓")
                return p
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx}: DALL·E failed: {e}")
            return await self._pollinations_with_retry(prompt, out_path, idx, job_id)

        elif image_source == "mixed":
            if idx == 0 and settings.has_pexels:
                try:
                    p = await self._pexels(search_query, out_path, idx)
                    if p:
                        logger.info(f"[{job_id}] img_{idx}: Pexels (mixed) ✓")
                        return p
                except Exception:
                    pass
            return await self._pollinations_with_retry(prompt, out_path, idx, job_id)

        else:
            # Default: pollinations
            return await self._pollinations_with_retry(prompt, out_path, idx, job_id)

    async def _pollinations_with_retry(self, prompt: str, out_path: str, idx: int, job_id: str) -> str:
        for attempt in range(3):
            try:
                p = await self._pollinations(prompt, out_path, seed=idx + attempt * 7)
                logger.info(f"[{job_id}] img_{idx}: Pollinations ✓ (attempt {attempt+1})")
                return p
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx} Pollinations attempt {attempt+1}: {e}")
                if attempt < 2:
                    await asyncio.sleep(4)

        logger.warning(f"[{job_id}] img_{idx}: all sources failed, using color fallback")
        return await self._color_fallback(out_path, idx)

    async def _pollinations(self, prompt: str, out_path: str, seed: int = 0) -> str:
        full = f"{prompt}, {self.STYLE}"
        encoded = urllib.parse.quote(full)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=576&height=1024&seed={seed}&nologo=true&enhance=true&model=flux"
        )
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "image" not in ct:
                raise RuntimeError(f"Not image: {ct[:40]}")
            if len(resp.content) < 5000:
                raise RuntimeError(f"Too small: {len(resp.content)} bytes")
            with open(out_path, "wb") as f:
                f.write(resp.content)
        return out_path

    async def _pexels(self, query: str, out_path: str, idx: int) -> str | None:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": settings.PEXELS_API_KEY},
                params={"query": query, "per_page": 10, "orientation": "portrait", "size": "large"},
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            if not photos:
                return None
            img_url = photos[idx % len(photos)]["src"]["large"]
            img_resp = await http.get(img_url, timeout=30)
            img_resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(img_resp.content)
        return out_path

    async def _dalle(self, prompt: str, out_path: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.images.generate(
            model="dall-e-3",
            prompt=f"{prompt}. {self.STYLE}"[:4000],
            size="1024x1792", quality="standard", n=1,
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
               "-i", f"color=c=#{c}:size=576x1024:rate=1",
               "-frames:v", "1", png]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.communicate()
        return png
