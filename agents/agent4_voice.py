"""
Agente 4: Gerador de Voz (TTS)
Suporta: edge-tts (gratuito online), Piper (offline), Coqui TTS, gTTS
FIXED: asyncio event loop compatibility com Gradio/Railway
"""

import logging
import subprocess
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from config.settings import (
    AUDIO_DIR, TTS_ENGINE,
    EDGE_TTS_VOICES, PIPER_VOICES_DIR, COQUI_MODEL
)

logger = logging.getLogger(__name__)


class VoiceAgent:
    """Agente responsável por gerar narração de voz para cada cena."""

    def __init__(self):
        self.engine = self._detect_engine()
        logger.info(f"VoiceAgent inicializado com engine: {self.engine}")

    def _detect_engine(self) -> str:
        preferred = TTS_ENGINE
        if preferred in ("edge-tts", "auto"):
            try:
                import edge_tts
                return "edge-tts"
            except ImportError:
                pass
        if preferred in ("gtts", "auto"):
            try:
                import gtts
                return "gtts"
            except ImportError:
                pass
        if preferred in ("piper", "auto"):
            if self._check_piper():
                return "piper"
        if preferred in ("coqui", "auto"):
            try:
                import TTS
                return "coqui"
            except ImportError:
                pass
        logger.warning("Nenhum engine TTS encontrado! Instala: pip install edge-tts")
        return "silent"

    def _check_piper(self) -> bool:
        try:
            result = subprocess.run(["piper", "--help"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _get_voice_key(self, voice_type: str, language: str) -> str:
        lang = language.lower()
        vtype = voice_type.lower()
        if "femini" in vtype or vtype == "female" or "pt_female" in vtype or "en_female" in vtype:
            key = f"{lang}_female"
        elif "masculi" in vtype or vtype == "male" or "pt_male" in vtype or "en_male" in vtype:
            key = f"{lang}_male"
        elif "robot" in vtype:
            key = "robotic"
        else:
            key = f"{lang}_female"
        return key

    def generate_audio(
        self,
        text: str,
        voice_type: str,
        language: str,
        scene_number: int,
        job_id: str = "",
        speed: float = 1.0
    ) -> Optional[Path]:
        logger.info(f"[{job_id}] Gerando áudio cena {scene_number} ({self.engine})")

        filename = f"{job_id}_scene{scene_number:02d}_audio.mp3"
        output_path = AUDIO_DIR / filename

        if output_path.exists() and output_path.stat().st_size > 100:
            logger.info(f"[{job_id}] Áudio cena {scene_number} em cache")
            return output_path

        success = False
        try:
            if self.engine == "edge-tts":
                success = self._generate_edge_tts(text, voice_type, language, output_path, speed)
            elif self.engine == "piper":
                success = self._generate_piper(text, voice_type, language, output_path, speed)
            elif self.engine == "coqui":
                success = self._generate_coqui(text, language, output_path, speed)
            elif self.engine == "gtts":
                success = self._generate_gtts(text, language, output_path, speed)
            else:
                success = self._generate_silent(5, output_path)
        except Exception as e:
            logger.error(f"[{job_id}] Engine {self.engine} falhou: {e}. Tentando gtts...")
            try:
                success = self._generate_gtts(text, language, output_path, speed)
            except Exception as e2:
                logger.error(f"[{job_id}] gtts também falhou: {e2}. Usando silêncio.")
                success = self._generate_silent(5, output_path)

        if success and output_path.exists() and output_path.stat().st_size > 100:
            logger.info(f"[{job_id}] ✓ Áudio gerado: {output_path}")
            return output_path

        logger.warning(f"[{job_id}] Áudio falhou, usando silêncio")
        self._generate_silent(5, output_path)
        return output_path if output_path.exists() else None

    def _generate_edge_tts(
        self, text: str, voice_type: str, language: str,
        output_path: Path, speed: float
    ) -> bool:
        """
        edge-tts via subprocess para evitar conflito de event loop com Gradio.
        """
        voice_key = self._get_voice_key(voice_type, language)
        voice_name = EDGE_TTS_VOICES.get(voice_key, EDGE_TTS_VOICES.get("pt_female", "pt-PT-RaquelNeural"))

        rate_percent = int((speed - 1.0) * 100)
        rate_str = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"

        # Usa subprocess para evitar asyncio.run() dentro do event loop do Gradio
        cmd = [
            sys.executable, "-c",
            f"""
import asyncio
import edge_tts

async def run():
    communicate = edge_tts.Communicate({repr(text)}, {repr(voice_name)}, rate={repr(rate_str)})
    await communicate.save({repr(str(output_path))})

asyncio.run(run())
"""
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=60, text=True)

        if result.returncode != 0:
            logger.warning(f"edge-tts subprocess erro: {result.stderr[:300]}")
            return False

        return output_path.exists() and output_path.stat().st_size > 100

    def _generate_piper(
        self, text: str, voice_type: str, language: str,
        output_path: Path, speed: float
    ) -> bool:
        piper_models = {
            "pt": "pt_PT-tugao-medium",
            "en": "en_US-lessac-medium",
            "es": "es_ES-mls_10246-low",
            "fr": "fr_FR-mls_1840-low",
        }
        model = piper_models.get(language, "en_US-lessac-medium")
        model_path = PIPER_VOICES_DIR / f"{model}.onnx"

        if not model_path.exists():
            logger.warning(f"Modelo Piper não encontrado: {model_path}")
            return False

        wav_path = output_path.with_suffix(".wav")
        cmd = [
            "piper", "--model", str(model_path),
            "--output_file", str(wav_path),
            "--length_scale", str(1.0 / speed)
        ]
        result = subprocess.run(cmd, input=text.encode(), capture_output=True, timeout=30)
        if result.returncode != 0:
            return False

        subprocess.run([
            "ffmpeg", "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame", "-qscale:a", "2", str(output_path)
        ], capture_output=True)
        wav_path.unlink(missing_ok=True)
        return output_path.exists()

    def _generate_coqui(self, text: str, language: str, output_path: Path, speed: float) -> bool:
        from TTS.api import TTS
        lang_models = {
            "pt": "tts_models/pt/cv/vits",
            "en": "tts_models/en/ljspeech/tacotron2-DDC",
            "es": "tts_models/es/css10/vits",
            "fr": "tts_models/fr/css10/vits",
        }
        model = lang_models.get(language, COQUI_MODEL)
        tts = TTS(model_name=model, progress_bar=False, gpu=False)
        wav_path = output_path.with_suffix(".wav")
        tts.tts_to_file(text=text, file_path=str(wav_path))
        subprocess.run([
            "ffmpeg", "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame", "-qscale:a", "2", str(output_path)
        ], capture_output=True)
        wav_path.unlink(missing_ok=True)
        return output_path.exists()

    def _generate_gtts(self, text: str, language: str, output_path: Path, speed: float) -> bool:
        from gtts import gTTS
        lang_map = {"pt": "pt", "en": "en", "es": "es", "fr": "fr"}
        lang = lang_map.get(language, "pt")
        tts = gTTS(text=text, lang=lang, slow=False)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        tts.save(tmp.name)
        shutil.move(tmp.name, str(output_path))
        return output_path.exists()

    def _generate_silent(self, duration: int, output_path: Path) -> bool:
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(duration),
            "-codec:a", "libmp3lame",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0

    def get_audio_duration(self, audio_path: Path) -> float:
        try:
            import json as _json
            result = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", str(audio_path)
            ], capture_output=True, text=True, timeout=10)
            data = _json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception:
            return 0.0

    def generate_batch(
        self, scenes: list, voice_type: str, language: str,
        job_id: str = "", speed: float = 1.0
    ) -> list:
        logger.info(f"[{job_id}] Gerando áudio para {len(scenes)} cenas")
        for i, scene in enumerate(scenes):
            path = self.generate_audio(
                text=scene["texto"],
                voice_type=voice_type,
                language=language,
                scene_number=scene["numero"],
                job_id=job_id,
                speed=speed
            )
            scene["audio_path"] = path
            if path:
                real_duration = self.get_audio_duration(path)
                if real_duration > 0:
                    scene["duracao_real"] = real_duration + 0.5
                    logger.info(f"[{job_id}] Cena {i+1}: áudio {real_duration:.1f}s")
            logger.info(f"[{job_id}] ✓ Áudio {i+1}/{len(scenes)}")
        return scenes
