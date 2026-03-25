"""
Agente 3: Gerador de Imagens com IA
FIXED: timeout aumentado, fallback robusto, placeholder sempre disponível
"""

import logging
import requests
import time
import hashlib
import io
from pathlib import Path
from typing import Optional
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from config.settings import (
    IMAGES_DIR, IMAGE_WIDTH, IMAGE_HEIGHT,
    SD_API_URL, SD_USE_LOCAL,
    POLLINATIONS_API,
    HF_API_TOKEN, HF_MODEL
)

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageEnhance, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow não instalado.")


class ImageAgent:
    """Agente responsável por gerar imagens com IA para cada cena."""

    def __init__(self):
        self.backend = self._detect_backend()
        logger.info(f"ImageAgent inicializado com backend: {self.backend}")

    def _detect_backend(self) -> str:
        # 1. SD local
        if SD_USE_LOCAL:
            try:
                r = requests.get(f"{SD_API_URL}/sdapi/v1/options", timeout=3)
                if r.status_code == 200:
                    return "sd_local"
            except Exception:
                pass

        # 2. Pollinations.ai - sempre tenta (não faz request de teste para não atrasar startup)
        return "pollinations"

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        scene_number: int = 1,
        job_id: str = ""
    ) -> Optional[Path]:
        logger.info(f"[{job_id}] Gerando imagem cena {scene_number} ({self.backend})")

        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        filename = f"{job_id}_scene{scene_number:02d}_{prompt_hash}.png"
        output_path = IMAGES_DIR / filename

        if output_path.exists() and output_path.stat().st_size > 1000:
            logger.info(f"[{job_id}] Imagem cena {scene_number} em cache")
            return output_path

        image_data = None
        backends_tried = []

        # Tenta cada backend por ordem
        for backend in ["sd_local", "pollinations", "huggingface", "placeholder"]:
            if backend == "sd_local" and not SD_USE_LOCAL:
                continue
            if backend == "huggingface" and not HF_API_TOKEN:
                continue

            backends_tried.append(backend)
            try:
                if backend == "sd_local":
                    image_data = self._generate_sd_local(prompt, negative_prompt)
                elif backend == "pollinations":
                    image_data = self._generate_pollinations(prompt)
                elif backend == "huggingface":
                    image_data = self._generate_huggingface(prompt, negative_prompt)
                elif backend == "placeholder":
                    image_data = self._generate_placeholder(prompt, scene_number)

                if image_data and len(image_data) > 1000:
                    logger.info(f"[{job_id}] ✓ Imagem gerada via {backend} ({len(image_data)} bytes)")
                    break
                else:
                    image_data = None
            except Exception as e:
                logger.warning(f"[{job_id}] Backend {backend} falhou: {e}")
                image_data = None

        if not image_data:
            logger.warning(f"[{job_id}] Todos os backends falharam. Placeholder de emergência.")
            image_data = self._generate_placeholder(prompt, scene_number)

        if image_data:
            return self._save_and_postprocess(image_data, output_path, job_id)

        return None

    def _generate_sd_local(self, prompt: str, negative_prompt: str) -> Optional[bytes]:
        import base64
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt or "blurry, low quality, watermark",
            "width": 576, "height": 1024,
            "steps": 20, "cfg_scale": 7.5,
            "sampler_name": "DPM++ 2M Karras",
            "n_iter": 1, "batch_size": 1,
        }
        r = requests.post(f"{SD_API_URL}/sdapi/v1/txt2img", json=payload, timeout=120)
        r.raise_for_status()
        result = r.json()
        if "images" in result and result["images"]:
            return base64.b64decode(result["images"][0])
        return None

    def _generate_pollinations(self, prompt: str, retries: int = 3) -> Optional[bytes]:
        import urllib.parse
        # Limita o prompt a 500 chars para evitar URLs enormes
        prompt_clean = prompt[:500]
        encoded = urllib.parse.quote(prompt_clean)
        url = f"{POLLINATIONS_API}/{encoded}?width=576&height=1024&nologo=true&model=flux"

        for attempt in range(retries):
            try:
                r = requests.get(url, timeout=45)
                if r.status_code == 200 and len(r.content) > 5000:
                    return r.content
                logger.warning(f"Pollinations tentativa {attempt+1}: status={r.status_code} size={len(r.content)}")
            except requests.Timeout:
                logger.warning(f"Pollinations timeout tentativa {attempt+1}")
            except Exception as e:
                logger.warning(f"Pollinations erro tentativa {attempt+1}: {e}")

            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))

        return None

    def _generate_huggingface(self, prompt: str, negative_prompt: str) -> Optional[bytes]:
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        payload = {
            "inputs": prompt,
            "parameters": {"negative_prompt": negative_prompt, "width": 576, "height": 1024}
        }
        api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
        r = requests.post(api_url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.content

    def _generate_placeholder(self, prompt: str, scene_number: int) -> Optional[bytes]:
        """Placeholder elegante com gradiente — sempre funciona sem internet."""
        if not PIL_AVAILABLE:
            # Fallback sem Pillow: cria PNG mínimo válido
            return self._minimal_png()

        palettes = [
            [(10, 10, 30), (100, 20, 80)],
            [(5, 15, 40), (20, 80, 120)],
            [(20, 5, 35), (80, 20, 100)],
            [(10, 25, 15), (20, 100, 60)],
            [(30, 10, 10), (120, 40, 20)],
        ]
        c1, c2 = palettes[scene_number % len(palettes)]

        img = Image.new("RGB", (576, 1024))
        pixels = img.load()
        for y in range(1024):
            t = y / 1024
            r = int(c1[0] * (1-t) + c2[0] * t)
            g = int(c1[1] * (1-t) + c2[1] * t)
            b = int(c1[2] * (1-t) + c2[2] * t)
            for x in range(576):
                pixels[x, y] = (r, g, b)

        # Texto central
        draw = ImageDraw.Draw(img)
        draw.text((288, 480), f"Cena {scene_number}", fill=(200, 200, 200), anchor="mm")
        draw.text((288, 520), "Gerando imagem...", fill=(120, 120, 120), anchor="mm")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _minimal_png(self) -> bytes:
        """PNG 1x1 preto válido como último fallback."""
        return (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
            b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
            b'\xd5N\x00\x00\x00\x00IEND\xaeB`\x82'
        )

    def _save_and_postprocess(self, image_data: bytes, output_path: Path, job_id: str) -> Path:
        if PIL_AVAILABLE:
            try:
                img = Image.open(io.BytesIO(image_data))
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img = img.resize((IMAGE_WIDTH, IMAGE_HEIGHT), Image.LANCZOS)
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(1.2)
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.08)
                img.save(output_path, "PNG", optimize=True)
            except Exception as e:
                logger.warning(f"[{job_id}] Erro no pós-processamento: {e}. Salvando raw.")
                with open(output_path, "wb") as f:
                    f.write(image_data)
        else:
            with open(output_path, "wb") as f:
                f.write(image_data)

        logger.info(f"[{job_id}] Imagem salva: {output_path} ({output_path.stat().st_size} bytes)")
        return output_path

    def generate_batch(self, scenes: list, job_id: str = "", delay: float = 1.5) -> list:
        logger.info(f"[{job_id}] Gerando imagens para {len(scenes)} cenas")
        from agents.agent2_scenes import SceneSplitterAgent
        neg_prompt = SceneSplitterAgent().get_negative_prompt()

        for i, scene in enumerate(scenes):
            try:
                path = self.generate_image(
                    prompt=scene["descricao_visual"],
                    negative_prompt=neg_prompt,
                    scene_number=scene["numero"],
                    job_id=job_id
                )
                scene["image_path"] = path
                logger.info(f"[{job_id}] ✓ Imagem {i+1}/{len(scenes)}")
            except Exception as e:
                logger.error(f"[{job_id}] ✗ Erro na imagem {i+1}: {e}")
                scene["image_path"] = None

            if i < len(scenes) - 1:
                time.sleep(delay)

        return scenes
