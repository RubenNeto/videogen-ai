"""
Agente 4: Gerador de Voz (TTS)
Suporta: edge-tts (gratuito online), Piper (offline), Coqui TTS, gTTS
"""

import logging
import asyncio
import subprocess
import os
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
        """Deteta o engine TTS disponível."""
        preferred = TTS_ENGINE

        if preferred == "edge-tts" or preferred == "auto":
            try:
                import edge_tts
                return "edge-tts"
            except ImportError:
                pass

        if preferred == "piper" or preferred == "auto":
            if self._check_piper():
                return "piper"

        if preferred == "coqui" or preferred == "auto":
            try:
                import TTS
                return "coqui"
            except ImportError:
                pass

        if preferred == "gtts" or preferred == "auto":
            try:
                import gtts
                return "gtts"
            except ImportError:
                pass

        logger.warning("Nenhum engine TTS encontrado! Instala: pip install edge-tts")
        return "silent"

    def _check_piper(self) -> bool:
        """Verifica se Piper TTS está instalado."""
        try:
            result = subprocess.run(
                ["piper", "--help"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_voice_key(self, voice_type: str, language: str) -> str:
        """Retorna a chave de voz correta para o engine."""
        lang = language.lower()
        vtype = voice_type.lower()

        # Mapeia para chave de voz
        if "femini" in vtype or vtype == "female":
            key = f"{lang}_female"
        elif "masculi" in vtype or vtype == "male":
            key = f"{lang}_male"
        elif "robot" in vtype:
            key = "robotic"
        else:
            key = f"{lang}_female"  # default

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
        """
        Gera áudio de narração para uma cena.

        Args:
            text: Texto a narrar
            voice_type: Tipo de voz (masculina, feminina, robótica)
            language: Idioma (pt, en, es, fr)
            scene_number: Número da cena
            job_id: ID do job
            speed: Velocidade da fala (0.8-1.3)

        Returns:
            Path para o ficheiro de áudio gerado
        """
        logger.info(f"[{job_id}] Gerando áudio cena {scene_number} ({self.engine})")

        filename = f"{job_id}_scene{scene_number:02d}_audio.mp3"
        output_path = AUDIO_DIR / filename

        if output_path.exists():
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
                success = self._generate_silent(scene_number, output_path)

        except Exception as e:
            logger.error(f"[{job_id}] Erro ao gerar áudio: {e}")
            # Cria áudio silencioso como fallback
            success = self._generate_silent(5, output_path)

        if success and output_path.exists():
            logger.info(f"[{job_id}] ✓ Áudio gerado: {output_path}")
            return output_path

        return None

    def _generate_edge_tts(
        self, text: str, voice_type: str, language: str,
        output_path: Path, speed: float
    ) -> bool:
        """
        Gera voz usando edge-tts (Microsoft Edge TTS, completamente gratuito).
        pip install edge-tts
        """
        import edge_tts

        voice_key = self._get_voice_key(voice_type, language)
        voice_name = EDGE_TTS_VOICES.get(voice_key, EDGE_TTS_VOICES.get("pt_female"))

        # Configura velocidade com SSML
        rate_percent = int((speed - 1.0) * 100)
        rate_str = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"

        # Efeito robótico via SSML (se solicitado)
        if "robot" in voice_type.lower():
            # Edge-tts com pitch alterado soa robótico
            ssml_text = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{language}">
                <voice name="{voice_name}">
                    <prosody rate="{rate_str}" pitch="-20Hz">{text}</prosody>
                </voice>
            </speak>"""
            communicate = edge_tts.Communicate(ssml_text, voice_name)
        else:
            communicate = edge_tts.Communicate(
                text, voice_name, rate=rate_str
            )

        # Executa async de forma síncrona
        async def _run():
            await communicate.save(str(output_path))

        asyncio.run(_run())
        return output_path.exists()

    def _generate_piper(
        self, text: str, voice_type: str, language: str,
        output_path: Path, speed: float
    ) -> bool:
        """
        Gera voz usando Piper TTS (offline, rápido e leve).
        Instalação: pip install piper-tts
        Modelos: https://huggingface.co/rhasspy/piper-voices
        """
        # Mapeamento de modelos Piper por idioma
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

        # Ficheiro WAV temporário
        wav_path = output_path.with_suffix(".wav")

        cmd = [
            "piper",
            "--model", str(model_path),
            "--output_file", str(wav_path),
            "--length_scale", str(1.0 / speed)
        ]

        result = subprocess.run(
            cmd,
            input=text.encode(),
            capture_output=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"Piper erro: {result.stderr.decode()}")
            return False

        # Converte WAV para MP3 via FFmpeg
        subprocess.run([
            "ffmpeg", "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            str(output_path)
        ], capture_output=True)

        wav_path.unlink(missing_ok=True)
        return output_path.exists()

    def _generate_coqui(
        self, text: str, language: str, output_path: Path, speed: float
    ) -> bool:
        """
        Gera voz usando Coqui TTS (open source, local).
        pip install TTS
        """
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

        # Converte para MP3
        subprocess.run([
            "ffmpeg", "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            str(output_path)
        ], capture_output=True)

        wav_path.unlink(missing_ok=True)
        return output_path.exists()

    def _generate_gtts(
        self, text: str, language: str, output_path: Path, speed: float
    ) -> bool:
        """
        Gera voz usando Google Text-to-Speech (gratuito, online).
        pip install gtts
        """
        from gtts import gTTS
        import tempfile

        tts = gTTS(text=text, lang=language, slow=(speed < 0.9))
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tts.save(tmp.name)

        # Ajusta velocidade com FFmpeg se necessário
        if speed != 1.0:
            subprocess.run([
                "ffmpeg", "-y", "-i", tmp.name,
                "-filter:a", f"atempo={speed}",
                str(output_path)
            ], capture_output=True)
            os.unlink(tmp.name)
        else:
            import shutil
            shutil.move(tmp.name, str(output_path))

        return output_path.exists()

    def _generate_silent(self, duration: int, output_path: Path) -> bool:
        """Cria áudio silencioso como último fallback."""
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(duration),
            "-codec:a", "libmp3lame",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0

    def get_audio_duration(self, audio_path: Path) -> float:
        """Obtém a duração real de um ficheiro de áudio."""
        try:
            result = subprocess.run([
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(audio_path)
            ], capture_output=True, text=True, timeout=10)

            import json
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception:
            return 0.0

    def generate_batch(
        self, scenes: list, voice_type: str, language: str,
        job_id: str = "", speed: float = 1.0
    ) -> list:
        """Gera áudio para todas as cenas."""
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

            # Obtém duração real do áudio e atualiza cena
            if path:
                real_duration = self.get_audio_duration(path)
                if real_duration > 0:
                    # Adiciona margem para a imagem durar um pouco mais que o áudio
                    scene["duracao_real"] = real_duration + 0.5
                    logger.info(f"[{job_id}] Cena {i+1}: áudio {real_duration:.1f}s")

            logger.info(f"[{job_id}] ✓ Áudio {i+1}/{len(scenes)}")

        return scenes
