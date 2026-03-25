"""
Agente 6: Montagem do Vídeo Final
Usa FFmpeg para montar imagens + áudio + legendas + música = vídeo TikTok
"""

import logging
import subprocess
import os
import shutil
import json
import time
import random
from pathlib import Path
from typing import List, Optional
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))
from config.settings import (
    VIDEOS_DIR, AUDIO_DIR, MUSIC_DIR,
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, VIDEO_FORMAT
)

logger = logging.getLogger(__name__)


class VideoAssemblerAgent:
    """Agente responsável por montar o vídeo final com FFmpeg."""

    def __init__(self):
        self._check_ffmpeg()
        logger.info("VideoAssemblerAgent inicializado")

    def _check_ffmpeg(self):
        """Verifica se FFmpeg está instalado."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError("FFmpeg não encontrado!")
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg não instalado! Instala em: https://ffmpeg.org/download.html"
            )

    def assemble_video(
        self,
        scenes: list,
        subtitle_path: Optional[Path],
        job_id: str,
        output_name: str,
        music_volume: float = 0.15,
        add_music: bool = True
    ) -> Optional[Path]:
        """
        Monta o vídeo final com todos os elementos.

        Args:
            scenes: Lista de cenas processadas (com image_path, audio_path)
            subtitle_path: Path para o ficheiro .ASS de legendas
            job_id: ID do job
            output_name: Nome do ficheiro de saída
            music_volume: Volume da música de fundo (0.0-1.0)
            add_music: Se deve adicionar música de fundo

        Returns:
            Path para o vídeo final
        """
        logger.info(f"[{job_id}] Iniciando montagem do vídeo: {output_name}")

        # Verifica cenas válidas
        valid_scenes = [s for s in scenes if s.get("image_path") or s.get("audio_path")]
        if not valid_scenes:
            logger.error(f"[{job_id}] Nenhuma cena válida para montar!")
            return None

        # Diretório temporário para ficheiros intermediários
        temp_dir = VIDEOS_DIR / f"temp_{job_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Passo 1: Cria clipes de vídeo por cena
            scene_clips = []
            for scene in valid_scenes:
                clip = self._create_scene_clip(scene, temp_dir, job_id)
                if clip:
                    scene_clips.append(clip)

            if not scene_clips:
                logger.error(f"[{job_id}] Nenhum clipe de cena gerado!")
                return None

            # Passo 2: Concatena todos os clipes
            concat_path = temp_dir / f"{job_id}_concat.mp4"
            self._concatenate_clips(scene_clips, concat_path, job_id)

            # Passo 3: Adiciona música de fundo (opcional)
            if add_music:
                with_music_path = temp_dir / f"{job_id}_with_music.mp4"
                music_file = self._find_music_file()
                if music_file:
                    self._add_background_music(
                        concat_path, music_file, with_music_path,
                        music_volume, job_id
                    )
                    if with_music_path.exists():
                        concat_path = with_music_path

            # Passo 4: Adiciona legendas (burn-in)
            final_path = VIDEOS_DIR / f"{output_name}.{VIDEO_FORMAT}"
            if subtitle_path and subtitle_path.exists():
                self._burn_subtitles(concat_path, subtitle_path, final_path, job_id)
            else:
                shutil.copy2(str(concat_path), str(final_path))

            # Passo 5: Pós-processamento (cor, brilho, TikTok-ready)
            if final_path.exists():
                self._post_process(final_path, job_id)

            logger.info(f"[{job_id}] ✓ Vídeo montado: {final_path}")
            return final_path

        except Exception as e:
            logger.error(f"[{job_id}] Erro na montagem: {e}", exc_info=True)
            return None
        finally:
            # Limpa temporários
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _create_scene_clip(
        self, scene: dict, temp_dir: Path, job_id: str
    ) -> Optional[Path]:
        """
        Cria clipe de vídeo para uma cena (imagem + áudio + efeito de câmara).
        """
        scene_num = scene.get("numero", 1)
        image_path = scene.get("image_path")
        audio_path = scene.get("audio_path")
        duration = scene.get("duracao_real", scene.get("duracao", 5))
        camera_effect = scene.get("camera_effect", "ken_burns")

        clip_path = temp_dir / f"scene_{scene_num:02d}.mp4"

        # Se não tem imagem, usa frame preto
        if not image_path or not Path(image_path).exists():
            logger.warning(f"[{job_id}] Cena {scene_num}: sem imagem, usando preto")
            image_path = None

        # Filtro de câmara (Ken Burns, zoom, pan)
        vf_filter = self._get_camera_filter(camera_effect, duration)

        # Constrói comando FFmpeg
        cmd = ["ffmpeg", "-y"]

        if image_path:
            cmd += [
                "-loop", "1",
                "-i", str(image_path),
            ]
        else:
            # Vídeo preto
            cmd += [
                "-f", "lavfi",
                "-i", f"color=black:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r={VIDEO_FPS}",
            ]

        if audio_path and Path(audio_path).exists():
            cmd += ["-i", str(audio_path)]
            audio_input = True
        else:
            # Áudio silencioso
            cmd += [
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100"
            ]
            audio_input = False

        # Parâmetros de vídeo
        cmd += [
            "-t", str(duration),
            "-vf", vf_filter,
            "-s", f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
            "-r", str(VIDEO_FPS),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(clip_path)
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=120)

        if result.returncode != 0:
            logger.error(f"[{job_id}] FFmpeg erro cena {scene_num}: {result.stderr.decode()[:500]}")
            return None

        return clip_path

    def _get_camera_filter(self, effect: str, duration: float) -> str:
        """Retorna o filtro FFmpeg para o efeito de câmara."""
        # Duração em frames
        frames = int(duration * VIDEO_FPS)

        filters = {
            "ken_burns": (
                f"scale={VIDEO_WIDTH * 2}:{VIDEO_HEIGHT * 2},"
                f"zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
            ),
            "zoom_in_slow": (
                f"scale={VIDEO_WIDTH * 2}:{VIDEO_HEIGHT * 2},"
                f"zoompan=z='min(zoom+0.002,1.4)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
            ),
            "zoom_out_slow": (
                f"scale={VIDEO_WIDTH * 2}:{VIDEO_HEIGHT * 2},"
                f"zoompan=z='if(eq(on,1),1.5,max(zoom-0.003,1))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
            ),
            "pan_right": (
                f"scale={VIDEO_WIDTH * 2}:{VIDEO_HEIGHT * 2},"
                f"zoompan=z=1.2:x='min(on*{VIDEO_WIDTH}/(2*{frames}),{VIDEO_WIDTH/2})':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
            ),
            "pan_left": (
                f"scale={VIDEO_WIDTH * 2}:{VIDEO_HEIGHT * 2},"
                f"zoompan=z=1.2:x='max({VIDEO_WIDTH/2}-on*{VIDEO_WIDTH}/(2*{frames}),0)':y='ih/2-(ih/zoom/2)'"
                f":d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS}"
            ),
            "static": (
                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
            ),
        }

        return filters.get(effect, filters["ken_burns"])

    def _concatenate_clips(
        self, clips: List[Path], output_path: Path, job_id: str
    ):
        """Concatena múltiplos clipes num único vídeo."""
        if len(clips) == 1:
            shutil.copy2(str(clips[0]), str(output_path))
            return

        # Cria ficheiro de lista para concatenação
        list_file = output_path.parent / f"{job_id}_list.txt"
        with open(list_file, "w") as f:
            for clip in clips:
                f.write(f"file '{clip.absolute()}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=300)

        list_file.unlink(missing_ok=True)

        if result.returncode != 0:
            raise RuntimeError(f"Erro na concatenação: {result.stderr.decode()[:500]}")

        logger.info(f"[{job_id}] {len(clips)} clipes concatenados")

    def _add_background_music(
        self,
        video_path: Path,
        music_path: Path,
        output_path: Path,
        volume: float,
        job_id: str
    ):
        """Adiciona música de fundo ao vídeo."""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-stream_loop", "-1",  # Loop música se necessário
            "-i", str(music_path),
            "-filter_complex",
            (
                f"[1:a]volume={volume},afade=t=in:st=0:d=1,"
                f"afade=t=out:st=999:d=2[music];"
                f"[0:a][music]amix=inputs=2:duration=first:weights=1 0.15[aout]"
            ),
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            logger.warning(f"[{job_id}] Erro ao adicionar música: {result.stderr.decode()[:300]}")
            shutil.copy2(str(video_path), str(output_path))

    def _burn_subtitles(
        self,
        video_path: Path,
        subtitle_path: Path,
        output_path: Path,
        job_id: str
    ):
        """Queima legendas ASS no vídeo (burn-in)."""
        # Escapa o path para FFmpeg
        sub_path_escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass='{sub_path_escaped}'",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "copy",
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=300)

        if result.returncode != 0:
            logger.warning(f"[{job_id}] Erro ao queimar legendas: {result.stderr.decode()[:300]}")
            shutil.copy2(str(video_path), str(output_path))

    def _post_process(self, video_path: Path, job_id: str):
        """
        Pós-processamento TikTok: cor, contraste, bitrate otimizado.
        Processa in-place.
        """
        temp_path = video_path.with_name(f"pp_{video_path.name}")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf",
            (
                # Melhora cor e vibração para TikTok
                "eq=brightness=0.05:saturation=1.15:contrast=1.08,"
                # Sharpening suave
                "unsharp=5:5:0.8:3:3:0.4"
            ),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-b:v", "4M",          # Bitrate alto para qualidade TikTok
            "-maxrate", "5M",
            "-bufsize", "10M",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-movflags", "+faststart",  # Otimiza para streaming
            str(temp_path)
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=300)

        if result.returncode == 0 and temp_path.exists():
            video_path.unlink()
            temp_path.rename(video_path)
            logger.info(f"[{job_id}] Pós-processamento concluído")
        else:
            if temp_path.exists():
                temp_path.unlink()

    def _find_music_file(self) -> Optional[Path]:
        """Encontra um ficheiro de música de fundo disponível."""
        supported = [".mp3", ".wav", ".ogg", ".m4a"]

        for ext in supported:
            files = list(MUSIC_DIR.glob(f"*{ext}"))
            if files:
                return random.choice(files)

        return None

    def get_video_info(self, video_path: Path) -> dict:
        """Obtém informação do vídeo gerado."""
        try:
            result = subprocess.run([
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(video_path)
            ], capture_output=True, text=True, timeout=10)

            data = json.loads(result.stdout)
            fmt = data.get("format", {})
            video_stream = next(
                (s for s in data.get("streams", []) if s["codec_type"] == "video"),
                {}
            )

            return {
                "duration": float(fmt.get("duration", 0)),
                "size_mb": round(int(fmt.get("size", 0)) / 1024 / 1024, 2),
                "width": video_stream.get("width", VIDEO_WIDTH),
                "height": video_stream.get("height", VIDEO_HEIGHT),
                "fps": eval(video_stream.get("r_frame_rate", "30/1")),
                "bitrate_kbps": round(int(fmt.get("bit_rate", 0)) / 1000),
            }
        except Exception:
            return {}
