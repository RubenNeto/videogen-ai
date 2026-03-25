"""
Pipeline Principal: Orquestra todos os 6 agentes
"""

import logging
import uuid
import json
import time
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


class VideoGenerationPipeline:
    """Orquestra o pipeline completo de geração de vídeos."""

    def __init__(self):
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
        """
        Executa o pipeline completo de geração de vídeo.

        Args:
            theme: Tema do vídeo
            duration: Duração em segundos (15, 30, 60)
            voice_type: Tipo de voz
            language: Idioma
            subtitle_style: Estilo de legendas
            topic: Tópico específico (opcional)
            add_music: Adicionar música de fundo
            music_volume: Volume da música
            job_id: ID único do job (gerado automaticamente se None)
            progress_callback: Função chamada com (step, total, message)

        Returns:
            Dict com resultado: {success, video_path, duration, info, error}
        """
        job_id = job_id or str(uuid.uuid4())[:8]
        start_time = time.time()

        # Setup logging por job
        log_path = LOGS_DIR / f"{job_id}_pipeline.log"
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        ))
        logger.addHandler(file_handler)

        def progress(step: int, total: int, msg: str):
            logger.info(f"[{job_id}] [{step}/{total}] {msg}")
            if progress_callback:
                progress_callback(step, total, msg, job_id)

        logger.info(f"[{job_id}] ═══ INICIANDO GERAÇÃO DE VÍDEO ═══")
        logger.info(f"[{job_id}] Tema: {theme} | Duração: {duration}s | Voz: {voice_type}")

        try:
            # ─── AGENTE 1: Geração de Script ──────────────────────────────
            progress(1, 6, "📝 Gerando script viral...")
            script = self.agent1.generate_script(
                theme=theme,
                duration=duration,
                language=language,
                topic=topic,
                job_id=job_id
            )
            self._save_json(script, LOGS_DIR / f"{job_id}_script.json")

            # ─── AGENTE 2: Divisão em Cenas ───────────────────────────────
            progress(2, 6, "🎬 Dividindo em cenas...")
            scenes = self.agent2.process_scenes(
                script=script,
                duration=duration,
                job_id=job_id
            )

            # ─── AGENTE 3: Geração de Imagens ─────────────────────────────
            progress(3, 6, f"🎨 Gerando {len(scenes)} imagens com IA...")
            scenes = self.agent3.generate_batch(
                scenes=scenes,
                job_id=job_id,
                delay=1.5
            )

            # ─── AGENTE 4: Geração de Voz ─────────────────────────────────
            progress(4, 6, "🔊 Gerando narração de voz...")
            scenes = self.agent4.generate_batch(
                scenes=scenes,
                voice_type=voice_type,
                language=language,
                job_id=job_id
            )

            # ─── AGENTE 5: Legendas ───────────────────────────────────────
            progress(5, 6, "💬 Criando legendas sincronizadas...")
            subtitle_path = LOGS_DIR / f"{job_id}_subtitles.ass"
            subtitle_path = self.agent5.process_all_scenes(
                scenes=scenes,
                style=subtitle_style,
                subtitle_path=subtitle_path,
                job_id=job_id
            )

            # ─── AGENTE 6: Montagem Final ─────────────────────────────────
            progress(6, 6, "🎥 Montando vídeo final...")
            output_name = self._generate_output_name(theme, duration, job_id)
            video_path = self.agent6.assemble_video(
                scenes=scenes,
                subtitle_path=subtitle_path,
                job_id=job_id,
                output_name=output_name,
                music_volume=music_volume,
                add_music=add_music
            )

            elapsed = round(time.time() - start_time, 1)

            if video_path and video_path.exists():
                video_info = self.agent6.get_video_info(video_path)
                logger.info(f"[{job_id}] ✅ Vídeo gerado em {elapsed}s: {video_path}")
                logger.info(f"[{job_id}] Info: {video_info}")

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
                    "error": None
                }
            else:
                raise RuntimeError("Vídeo não foi gerado corretamente")

        except Exception as e:
            elapsed = round(time.time() - start_time, 1)
            logger.error(f"[{job_id}] ❌ Erro no pipeline: {e}", exc_info=True)
            return {
                "success": False,
                "job_id": job_id,
                "video_path": None,
                "error": str(e),
                "elapsed_seconds": elapsed,
                "log_path": str(log_path)
            }
        finally:
            logger.removeHandler(file_handler)

    def generate_batch(
        self,
        configs: list,
        progress_callback=None
    ) -> list:
        """
        Gera múltiplos vídeos em sequência (batch).

        Args:
            configs: Lista de dicts com configurações por vídeo
            progress_callback: Callback de progresso

        Returns:
            Lista de resultados
        """
        results = []
        total = len(configs)

        logger.info(f"Iniciando geração em lote: {total} vídeos")

        for i, config in enumerate(configs):
            logger.info(f"Batch {i+1}/{total}: {config.get('theme', 'unknown')}")

            result = self.generate_video(**config, progress_callback=progress_callback)
            results.append(result)

            if result["success"]:
                logger.info(f"✅ Batch {i+1}/{total} completo: {result['video_name']}")
            else:
                logger.error(f"❌ Batch {i+1}/{total} falhou: {result['error']}")

        successful = sum(1 for r in results if r["success"])
        logger.info(f"Batch completo: {successful}/{total} vídeos gerados com sucesso")

        return results

    def _generate_output_name(self, theme: str, duration: int, job_id: str) -> str:
        """Gera nome único para o vídeo."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"tiktok_{theme}_{duration}s_{timestamp}_{job_id}"

    def _save_json(self, data: dict, path: Path):
        """Salva dados JSON para debug/logging."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
