"""
Pipeline Principal: Orquestra todos os 6 agentes
FIXED: Melhor tratamento de erros, diagnósticos, filesystem seguro
"""

import logging
import uuid
import json
import time
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from config.settings import VIDEOS_DIR, LOGS_DIR
from agents.agent1_script import ScriptAgent
from agents.agent2_scenes import SceneSplitterAgent
from agents.agent3_images import ImageAgent
from agents.agent4_voice import VoiceAgent
from agents.agent5_subtitles import SubtitleAgent
from agents.agent6_video import VideoAssemblerAgent

logger = logging.getLogger(__name__)


def ensure_dirs():
    """Garante que todos os diretórios necessários existem (crítico no Railway)."""
    from config.settings import (
        VIDEOS_DIR, IMAGES_DIR, AUDIO_DIR, LOGS_DIR,
        MUSIC_DIR, FONTS_DIR, TEMPLATES_DIR, QUEUE_DIR
    )
    for d in [VIDEOS_DIR, IMAGES_DIR, AUDIO_DIR, LOGS_DIR, MUSIC_DIR, FONTS_DIR, TEMPLATES_DIR, QUEUE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def get_system_diagnostics() -> Dict[str, Any]:
    """Retorna diagnóstico completo do sistema."""
    import subprocess, shutil

    diag = {
        "timestamp": datetime.now().isoformat(),
        "python_version": sys.version,
        "ffmpeg": False,
        "ffprobe": False,
        "edge_tts": False,
        "gtts": False,
        "pillow": False,
        "requests": False,
        "pollinations_reachable": False,
        "groq_key_set": bool(os.environ.get("GROQ_API_KEY")),
        "ollama_url": os.environ.get("OLLAMA_URL", "not set"),
        "tts_engine": os.environ.get("TTS_ENGINE", "edge-tts"),
        "disk_writable": False,
        "env_vars": {
            "GROQ_API_KEY": "SET" if os.environ.get("GROQ_API_KEY") else "NOT SET",
            "TTS_ENGINE": os.environ.get("TTS_ENGINE", "not set"),
            "SD_USE_LOCAL": os.environ.get("SD_USE_LOCAL", "not set"),
            "PORT": os.environ.get("PORT", "not set"),
        }
    }

    # FFmpeg
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        diag["ffmpeg"] = r.returncode == 0
        diag["ffprobe"] = shutil.which("ffprobe") is not None
    except Exception:
        pass

    # Python packages
    try:
        import edge_tts; diag["edge_tts"] = True
    except ImportError:
        pass
    try:
        import gtts; diag["gtts"] = True
    except ImportError:
        pass
    try:
        from PIL import Image; diag["pillow"] = True
    except ImportError:
        pass
    try:
        import requests; diag["requests"] = True
    except ImportError:
        pass

    # Pollinations reachability
    try:
        import requests as req
        r = req.get("https://image.pollinations.ai/prompt/test?width=64&height=64&nologo=true", timeout=10)
        diag["pollinations_reachable"] = r.status_code == 200
    except Exception as e:
        diag["pollinations_error"] = str(e)[:100]

    # Disk write test
    try:
        test_file = VIDEOS_DIR / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        diag["disk_writable"] = True
    except Exception as e:
        diag["disk_error"] = str(e)[:100]

    return diag


class VideoGenerationPipeline:
    """Orquestra o pipeline completo de geração de vídeos."""

    def __init__(self):
        ensure_dirs()
        logger.info("Inicializando Pipeline...")
        self.agent1 = ScriptAgent()
        self.agent2 = SceneSplitterAgent()
        self.agent3 = ImageAgent()
        self.agent4 = VoiceAgent()
        self.agent5 = SubtitleAgent()
        self.agent6 = VideoAssemblerAgent()
        logger.info("Pipeline pronto!")

    def generate_video(
        self,
        theme: str,
        duration: int,
        voice_type: str = "pt_female",
        language: str = "pt",
        subtitle_style: str = "tiktok",
        topic: Optional[str] = None,
        add_music: bool = True,
        music_volume: float = 0.15,
        job_id: Optional[str] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        job_id = job_id or str(uuid.uuid4())[:8]
        start_time = time.time()
        ensure_dirs()

        log_path = LOGS_DIR / f"{job_id}_pipeline.log"
        try:
            file_handler = logging.FileHandler(log_path)
            file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            logger.addHandler(file_handler)
        except Exception:
            file_handler = None

        def progress(step: int, total: int, msg: str):
            logger.info(f"[{job_id}] [{step}/{total}] {msg}")
            if progress_callback:
                try:
                    progress_callback(step, total, msg, job_id)
                except Exception:
                    pass

        logger.info(f"[{job_id}] ═══ INICIANDO GERAÇÃO ═══ tema={theme} dur={duration}s voz={voice_type}")

        try:
            # AGENTE 1: Script
            progress(1, 6, "📝 A escrever script viral...")
            script = self.agent1.generate_script(
                theme=theme, duration=duration,
                language=language, topic=topic, job_id=job_id
            )
            self._save_json(script, LOGS_DIR / f"{job_id}_script.json")
            logger.info(f"[{job_id}] Script: {len(script.get('cenas',[]))} cenas, hook='{script.get('hook','')[:50]}'")

            # AGENTE 2: Cenas
            progress(2, 6, "🎬 A dividir em cenas...")
            scenes = self.agent2.process_scenes(script=script, duration=duration, job_id=job_id)
            logger.info(f"[{job_id}] {len(scenes)} cenas processadas")

            # AGENTE 3: Imagens
            progress(3, 6, f"🎨 A gerar {len(scenes)} imagens com IA...")
            scenes = self.agent3.generate_batch(scenes=scenes, job_id=job_id, delay=1.0)
            ok_imgs = sum(1 for s in scenes if s.get("image_path"))
            logger.info(f"[{job_id}] {ok_imgs}/{len(scenes)} imagens geradas")

            # AGENTE 4: Voz
            progress(4, 6, "🔊 A gerar narração...")
            scenes = self.agent4.generate_batch(
                scenes=scenes, voice_type=voice_type,
                language=language, job_id=job_id
            )
            ok_audio = sum(1 for s in scenes if s.get("audio_path"))
            logger.info(f"[{job_id}] {ok_audio}/{len(scenes)} áudios gerados")

            # AGENTE 5: Legendas
            progress(5, 6, "💬 A criar legendas...")
            subtitle_path = LOGS_DIR / f"{job_id}_subtitles.ass"
            subtitle_path = self.agent5.process_all_scenes(
                scenes=scenes, style=subtitle_style,
                subtitle_path=subtitle_path, job_id=job_id
            )

            # AGENTE 6: Vídeo
            progress(6, 6, "🎥 A montar vídeo final...")
            output_name = self._generate_output_name(theme, duration, job_id)
            video_path = self.agent6.assemble_video(
                scenes=scenes, subtitle_path=subtitle_path,
                job_id=job_id, output_name=output_name,
                music_volume=music_volume, add_music=add_music
            )

            elapsed = round(time.time() - start_time, 1)

            if video_path and video_path.exists() and video_path.stat().st_size > 10000:
                video_info = self.agent6.get_video_info(video_path)
                logger.info(f"[{job_id}] ✅ SUCESSO em {elapsed}s — {video_path} ({video_info.get('size_mb',0):.1f}MB)")
                return {
                    "success": True,
                    "job_id": job_id,
                    "video_path": str(video_path),
                    "video_name": video_path.name,
                    "script": script,
                    "scenes_count": len(scenes),
                    "duration_real": video_info.get("duration", duration),
                    "size_mb": video_info.get("size_mb", 0),
                    "elapsed_seconds": elapsed,
                    "log_path": str(log_path),
                    "error": None,
                    "images_generated": ok_imgs,
                    "audio_generated": ok_audio,
                }
            else:
                size = video_path.stat().st_size if video_path and video_path.exists() else 0
                raise RuntimeError(f"Vídeo gerado mas inválido (tamanho: {size} bytes). Verifica FFmpeg.")

        except Exception as e:
            elapsed = round(time.time() - start_time, 1)
            logger.error(f"[{job_id}] ❌ ERRO após {elapsed}s: {e}", exc_info=True)
            return {
                "success": False,
                "job_id": job_id,
                "video_path": None,
                "error": str(e),
                "elapsed_seconds": elapsed,
                "log_path": str(log_path),
            }
        finally:
            if file_handler:
                try:
                    logger.removeHandler(file_handler)
                    file_handler.close()
                except Exception:
                    pass

    def generate_batch(self, configs: list, progress_callback=None) -> list:
        results = []
        for i, config in enumerate(configs):
            logger.info(f"Batch {i+1}/{len(configs)}")
            result = self.generate_video(**config, progress_callback=progress_callback)
            results.append(result)
        return results

    def _generate_output_name(self, theme: str, duration: int, job_id: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"tiktok_{theme}_{duration}s_{timestamp}_{job_id}"

    def _save_json(self, data: dict, path: Path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
