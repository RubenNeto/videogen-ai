"""
Agent 4: Visual Agent
Uses Pollinations.ai model=turbo (5-10x faster than flux).
Smaller resolution (432x768) then upscaled by FFmpeg -> faster generation.
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

# Smaller size = faster Pollinations response, FFmpeg upscales to 576x1024
POLL_W, POLL_H = 432, 768


class VisualAgent:

    async def generate(self, script: dict, job_id: str = "", image_source: str = "pollinations") -> list[str]:
        prompts = script.get("image_prompts", [])
        niche   = script.get("niche", "cinematic")

        # Ensure 4 prompts
        while len(prompts) < 4:
            prompts.append({"prompt": f"{niche} cinematic dramatic"})

        logger.info(f"[{job_id}] {len(prompts[:4])} images | source={image_source}")

        results = []
        for idx, ip in enumerate(prompts[:4]):
            path = await self._get_image(ip, idx, job_id, image_source, niche)
            results.append(path)

        valid = [r for r in results if r and os.path.exists(r)]
        if not valid:
            raise RuntimeError(f"[{job_id}] All images failed")

        logger.info(f"[{job_id}] {len(valid)}/4 images OK")
        return valid

    async def _get_image(self, ip: dict, idx: int, job_id: str, source: str, niche: str) -> str:
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"img_{idx:02d}_{uuid.uuid4().hex[:6]}.jpg")

        prompt = self._clean(ip.get("prompt", ip.get("search_query", niche)), niche)

        # Route by source
        if source == "pexels" and settings.has_pexels:
            result = await self._pexels(ip.get("search_query", niche), out_path, idx)
            if result:
                return result
            logger.warning(f"[{job_id}] img_{idx}: Pexels failed, falling back to Pollinations")

        elif source == "dalle" and settings.OPENAI_API_KEY:
            try:
                return await self._dalle(prompt, out_path.replace(".jpg", ".png"))
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx}: DALL·E failed: {e}")

        # Pollinations — try turbo first (fast), then flux (better quality)
        for model in ["turbo", "flux"]:
            for attempt in range(2):
                try:
                    p = await self._pollinations(prompt, out_path, seed=idx * 7 + attempt, model=model)
                    logger.info(f"[{job_id}] img_{idx}: Pollinations/{model} ✓")
                    return p
                except Exception as e:
                    logger.warning(f"[{job_id}] img_{idx} {model} #{attempt+1}: {e}")
                    await asyncio.sleep(2)

        # Absolute fallback — dark gradient (FFmpeg, always works)
        logger.warning(f"[{job_id}] img_{idx}: using gradient fallback")
        return await self._gradient_fallback(out_path, idx, niche)

    def _clean(self, prompt: str, niche: str) -> str:
        clean = re.sub(
            r'(no text|no watermark|no logo|vertical|9:16|portrait|ultra sharp|'
            r'professional|high quality|photorealistic|cinematic lighting|dramatic lighting)',
            '', prompt, flags=re.IGNORECASE
        )
        clean = re.sub(r'\s+', ' ', clean).strip().strip(',.')[:60]
        return clean or niche

    async def _pollinations(self, prompt: str, out_path: str, seed: int, model: str = "turbo") -> str:
        full    = f"{prompt}, cinematic, dramatic"
        encoded = urllib.parse.quote(full)
        # Use smaller size for faster generation
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={POLL_W}&height={POLL_H}&seed={seed}&nologo=true&model={model}"
        )
        logger.debug(f"Pollinations {model}: {url[:80]}")

        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "image" not in ct:
                raise RuntimeError(f"Not image: {ct[:40]}")
            if len(resp.content) < 3000:
                raise RuntimeError(f"Too small: {len(resp.content)}B")
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
                img = await http.get(photos[idx % len(photos)]["src"]["large"], timeout=30)
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

    async def _gradient_fallback(self, out_path: str, idx: int, niche: str) -> str:
        """
        Dark gradient with text overlay — always works, looks better than solid color.
        Uses FFmpeg drawtext filter.
        """
        colors = ["#0f0c29", "#1a1a2e", "#16213e", "#0f3460"]
        color  = colors[idx % len(colors)]
        png    = out_path.replace(".jpg", ".png")
        # Create gradient with niche text
        short  = (niche[:20] if niche else "VIDEO").upper()
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c={color}:size=576x1024:rate=1",
            "-vf", (
                f"drawtext=text='{short}':fontsize=40:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:"
                f"shadowx=2:shadowy=2:shadowcolor=black"
            ),
            "-frames:v", "1", png
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()
        if not os.path.exists(png):
            # Absolute last resort - plain color
            cmd2 = ["ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"color=c={color}:size=576x1024:rate=1",
                    "-frames:v", "1", png]
            proc2 = await asyncio.create_subprocess_exec(*cmd2,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc2.communicate()
        return png
