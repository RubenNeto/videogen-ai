"""
Agente 3: Gerador de Imagens com IA
Usa múltiplas fontes gratuitas: Pollinations.ai, Stable Diffusion local, Hugging Face
"""

import logging
import requests
import time
import hashlib
import base64
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
    from PIL import Image, ImageFilter, ImageEnhance
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow não instalado. Pós-processamento desativado.")


class ImageAgent:
    """Agente responsável por gerar imagens com IA para cada cena."""

    def __init__(self):
        self.backend = self._detect_backend()
        logger.info(f"ImageAgent inicializado com backend: {self.backend}")

    def _detect_backend(self) -> str:
        """Deteta o backend de geração de imagens disponível."""
        # 1. Tenta Stable Diffusion local (AUTOMATIC1111)
        if SD_USE_LOCAL:
            try:
                r = requests.get(f"{SD_API_URL}/sdapi/v1/options", timeout=3)
                if r.status_code == 200:
                    logger.info("Stable Diffusion local (AUTOMATIC1111) detetado!")
                    return "sd_local"
            except Exception:
                pass

        # 2. Pollinations.ai (completamente gratuito, sem chave)
        try:
            test_url = f"{POLLINATIONS_API}/test?width=64&height=64&nologo=true"
            r = requests.get(test_url, timeout=10)
            if r.status_code == 200:
                logger.info("Pollinations.ai disponível")
                return "pollinations"
        except Exception:
            pass

        # 3. Hugging Face Inference API
        if HF_API_TOKEN:
            return "huggingface"

        # 4. Fallback: gradiente colorido
        logger.warning("Nenhum backend de IA disponível. Usando imagens de placeholder.")
        return "placeholder"

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        scene_number: int = 1,
        job_id: str = ""
    ) -> Optional[Path]:
        """
        Gera uma imagem para uma cena.

        Args:
            prompt: Descrição da imagem
            negative_prompt: O que evitar na imagem
            scene_number: Número da cena (para nomenclatura)
            job_id: ID do job

        Returns:
            Path para a imagem gerada
        """
        logger.info(f"[{job_id}] Gerando imagem cena {scene_number} ({self.backend})")

        # Nome único do ficheiro
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        filename = f"{job_id}_scene{scene_number:02d}_{prompt_hash}.png"
        output_path = IMAGES_DIR / filename

        # Se já existe (cache), reutiliza
        if output_path.exists():
            logger.info(f"[{job_id}] Imagem cena {scene_number} encontrada em cache")
            return output_path

        # Gera imagem com o backend disponível
        image_data = None
        try:
            if self.backend == "sd_local":
                image_data = self._generate_sd_local(prompt, negative_prompt)
            elif self.backend == "pollinations":
                image_data = self._generate_pollinations(prompt)
            elif self.backend == "huggingface":
                image_data = self._generate_huggingface(prompt, negative_prompt)
            else:
                image_data = self._generate_placeholder(prompt, scene_number)

        except Exception as e:
            logger.error(f"[{job_id}] Erro ao gerar imagem: {e}. Usando placeholder.")
            image_data = self._generate_placeholder(prompt, scene_number)

        if image_data:
            # Salva e pós-processa
            saved_path = self._save_and_postprocess(image_data, output_path, job_id)
            return saved_path

        return None

    def _generate_sd_local(self, prompt: str, negative_prompt: str) -> Optional[bytes]:
        """Gera imagem via Stable Diffusion local (AUTOMATIC1111 WebUI)."""
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt or "blurry, low quality, watermark",
            "width": 576,      # SD gera menor e fazemos upscale
            "height": 1024,    # Ratio 9:16
            "steps": 20,
            "cfg_scale": 7.5,
            "sampler_name": "DPM++ 2M Karras",
            "n_iter": 1,
            "batch_size": 1,
        }

        r = requests.post(
            f"{SD_API_URL}/sdapi/v1/txt2img",
            json=payload,
            timeout=120
        )
        r.raise_for_status()

        result = r.json()
        if "images" in result and result["images"]:
            return base64.b64decode(result["images"][0])
        return None

    def _generate_pollinations(self, prompt: str, retries: int = 3) -> Optional[bytes]:
        """
        Gera imagem via Pollinations.ai (100% gratuito, sem registo).
        URL: https://image.pollinations.ai/prompt/{prompt}?params
        """
        # Codifica o prompt para URL
        import urllib.parse
        encoded = urllib.parse.quote(prompt)

        # Parâmetros
        params = {
            "width": 576,
            "height": 1024,
            "nologo": "true",
            "enhance": "true",
            "model": "flux",  # Modelo mais recente disponível
        }
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{POLLINATIONS_API}/{encoded}?{param_str}"

        for attempt in range(retries):
            try:
                r = requests.get(url, timeout=60)
                if r.status_code == 200 and len(r.content) > 1000:
                    return r.content
                else:
                    logger.warning(f"Pollinations: status {r.status_code}, tentativa {attempt+1}")
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"Pollinations erro: {e}, tentativa {attempt+1}")
                time.sleep(2 ** attempt)

        return None

    def _generate_huggingface(self, prompt: str, negative_prompt: str) -> Optional[bytes]:
        """Gera imagem via Hugging Face Inference API (gratuita com token)."""
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        payload = {
            "inputs": prompt,
            "parameters": {
                "negative_prompt": negative_prompt,
                "width": 576,
                "height": 1024,
                "num_inference_steps": 20,
            }
        }

        api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
        r = requests.post(api_url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.content

    def _generate_placeholder(self, prompt: str, scene_number: int) -> Optional[bytes]:
        """Cria uma imagem placeholder colorida quando nenhum backend está disponível."""
        if not PIL_AVAILABLE:
            logger.error("Pillow não instalado para criar placeholder")
            return None

        import io
        from PIL import Image, ImageDraw, ImageFont
        import random

        # Paleta de cores por cena
        colors = [
            ("#1a1a2e", "#e94560"),
            ("#0f3460", "#533483"),
            ("#16213e", "#0f3460"),
            ("#1b262c", "#0f4c75"),
            ("#2d132c", "#c72c41"),
        ]
        bg_color, accent_color = colors[scene_number % len(colors)]

        img = Image.new("RGB", (576, 1024), bg_color)
        draw = ImageDraw.Draw(img)

        # Gradiente simples
        for y in range(1024):
            alpha = y / 1024
            r1, g1, b1 = int(bg_color[1:3], 16), int(bg_color[3:5], 16), int(bg_color[5:7], 16)
            r2, g2, b2 = int(accent_color[1:3], 16), int(accent_color[3:5], 16), int(accent_color[5:7], 16)
            r = int(r1 * (1 - alpha) + r2 * alpha)
            g = int(g1 * (1 - alpha) + g2 * alpha)
            b = int(b1 * (1 - alpha) + b2 * alpha)
            draw.line([(0, y), (576, y)], fill=(r, g, b))

        # Texto de placeholder
        draw.text((50, 450), f"Cena {scene_number}", fill="white")
        draw.text((50, 500), prompt[:60] + "...", fill=(200, 200, 200))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _save_and_postprocess(
        self, image_data: bytes, output_path: Path, job_id: str
    ) -> Path:
        """Salva a imagem e aplica pós-processamento (resize, sharpening, etc.)."""
        if PIL_AVAILABLE:
            import io
            img = Image.open(io.BytesIO(image_data))

            # Converte para RGB se necessário
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Redimensiona para 1080x1920 (TikTok)
            img = img.resize((IMAGE_WIDTH, IMAGE_HEIGHT), Image.LANCZOS)

            # Melhora nitidez
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.3)

            # Aumenta ligeiramente o contraste
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.1)

            img.save(output_path, "PNG", optimize=True)
        else:
            # Salva raw se Pillow não disponível
            with open(output_path, "wb") as f:
                f.write(image_data)

        logger.info(f"[{job_id}] Imagem salva: {output_path}")
        return output_path

    def generate_batch(
        self, scenes: list, job_id: str = "", delay: float = 1.0
    ) -> list:
        """
        Gera imagens para múltiplas cenas em sequência.

        Args:
            scenes: Lista de cenas (do Agent 2)
            job_id: ID do job
            delay: Delay entre gerações (evita rate limiting)

        Returns:
            Lista de cenas com image_path preenchido
        """
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
                logger.info(f"[{job_id}] ✓ Imagem {i+1}/{len(scenes)} gerada")
            except Exception as e:
                logger.error(f"[{job_id}] ✗ Erro na imagem {i+1}: {e}")
                scene["image_path"] = None

            # Delay para não sobrecarregar APIs gratuitas
            if i < len(scenes) - 1:
                time.sleep(delay)

        return scenes
