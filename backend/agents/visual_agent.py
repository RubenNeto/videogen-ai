"""
Agent 4: Visual Agent
Priority: Pexels (real photos) → DALL·E 3 → Stability AI
Uses niche-specific search queries from the script for accurate results.
"""
import asyncio
import base64
import logging
import os
import uuid
import httpx
from backend.utils.config import settings

logger = logging.getLogger(__name__)


class VisualAgent:

    PORTRAIT_STYLE = (
        "vertical 9:16 portrait format, "
        "photorealistic, cinematic lighting, sharp focus, "
        "high quality social media visual, no text overlays, no watermarks"
    )

    async def generate(self, script: dict, job_id: str = "") -> list[str]:
        """
        Generate images for each scene. Returns list of local file paths.
        Strategy: Pexels (real photos) → DALL·E 3 → Stability AI
        """
        image_prompts = script.get("image_prompts", [])
        niche = script.get("niche", "")

        if not image_prompts:
            # Fallback: create basic prompts from body segments
            image_prompts = [
                {"prompt": seg.get("visual_note", niche), "search_query": niche, "mood": "neutral"}
                for seg in script.get("body", [{"visual_note": niche}])
            ]

        logger.info(f"[{job_id}] Generating {len(image_prompts)} images (source priority: pexels→dalle→stability)")

        tasks = [
            self._get_image(ip, idx, job_id)
            for idx, ip in enumerate(image_prompts)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid = [r for r in results if isinstance(r, str) and os.path.exists(r)]
        if not valid:
            raise RuntimeError(f"[{job_id}] All {len(image_prompts)} image generation attempts failed")

        logger.info(f"[{job_id}] Got {len(valid)}/{len(image_prompts)} images")
        return valid

    async def _get_image(self, image_prompt: dict, idx: int, job_id: str) -> str:
        """Try sources in priority order."""
        out_dir = os.path.join(settings.TEMP_DIR, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"img_{idx:02d}_{uuid.uuid4().hex[:6]}.jpg")

        search_query = image_prompt.get("search_query", "")
        ai_prompt = image_prompt.get("prompt", search_query)

        # 1. Pexels (free, real photos)
        if settings.has_pexels and search_query:
            try:
                path = await self._pexels(search_query, out_path, idx)
                if path:
                    logger.info(f"[{job_id}] img_{idx}: Pexels ✓ ({search_query})")
                    return path
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx}: Pexels failed: {e}")

        # 2. DALL·E 3
        if settings.OPENAI_API_KEY:
            try:
                path = await self._dalle(ai_prompt, out_path.replace(".jpg", ".png"))
                logger.info(f"[{job_id}] img_{idx}: DALL·E ✓")
                return path
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx}: DALL·E failed: {e}")

        # 3. Stability AI
        if settings.has_stability:
            try:
                path = await self._stability(ai_prompt, out_path.replace(".jpg", ".png"))
                logger.info(f"[{job_id}] img_{idx}: Stability ✓")
                return path
            except Exception as e:
                logger.warning(f"[{job_id}] img_{idx}: Stability failed: {e}")

        # Last resort: create a solid color image with FFmpeg (no API needed)
        try:
            return await self._color_fallback(out_path, idx)
        except Exception:
            raise RuntimeError(f"All image sources failed for index {idx}")

    async def _pexels(self, query: str, out_path: str, idx: int) -> str | None:
        """Fetch a relevant photo from Pexels. Returns path or None."""
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": settings.PEXELS_API_KEY},
                params={
                    "query": query,
                    "per_page": 10,
                    "orientation": "portrait",   # 9:16 friendly
                    "size": "large",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            photos = data.get("photos", [])

            if not photos:
                # Try broader query (first word only)
                return None

            # Cycle through results to avoid same photo every time
            photo = photos[idx % len(photos)]
            img_url = photo["src"]["large2x"]  # High-res portrait

            img_resp = await http.get(img_url, timeout=30)
            img_resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(img_resp.content)
            return out_path

    async def _dalle(self, prompt: str, out_path: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        enhanced = f"{prompt}. {self.PORTRAIT_STYLE}"
        resp = await client.images.generate(
            model="dall-e-3",
            prompt=enhanced[:4000],
            size="1024x1792",  # 9:16 ratio
            quality="standard",
            n=1,
        )
        img_url = resp.data[0].url
        async with httpx.AsyncClient(timeout=30) as http:
            img_resp = await http.get(img_url)
            img_resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(img_resp.content)
        return out_path

    async def _stability(self, prompt: str, out_path: str) -> str:
        enhanced = f"{prompt}. {self.PORTRAIT_STYLE}"
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                headers={
                    "Authorization": f"Bearer {settings.STABILITY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "text_prompts": [{"text": enhanced, "weight": 1}],
                    "cfg_scale": 7,
                    "height": 1344,
                    "width": 768,
                    "samples": 1,
                    "steps": 30,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            img_data = base64.b64decode(data["artifacts"][0]["base64"])
            with open(out_path, "wb") as f:
                f.write(img_data)
        return out_path
    async def _color_fallback(self, out_path: str, idx: int) -> str:
        """Cria imagem sólida como último recurso (sem API necessária)."""
        import asyncio
        colors = ["#1a1a2e", "#16213e", "#0f3460", "#533483", "#2d132c"]
        color = colors[idx % len(colors)]
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={color}:size=1080x1920:rate=1",
            "-frames:v", "1",
            out_path.replace(".jpg", ".png"),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        final = out_path.replace(".jpg", ".png")
        logger.warning(f"Using color fallback image: {final}")
        return final

