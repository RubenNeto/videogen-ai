"""
Agent 6: Video Assembly — Creashort style
- 576x1024 @ 24fps (TikTok native)
- Legendas dinâmicas: 1-2 palavras por vez, centradas, estilo Creashort
- Ken Burns effect nas imagens (zoom lento)
- Ritmo de corte rápido (2-3s por imagem)
- Respeita duração alvo
"""
import asyncio
import json
import logging
import os
import shutil
import uuid
from backend.utils.config import settings

logger = logging.getLogger(__name__)

W, H = 576, 1024
FPS  = 24


class VideoAssemblyAgent:

    async def assemble(self, image_paths, audio_path, script, job_id="") -> dict:
        if not image_paths:
            raise ValueError(f"[{job_id}] No images")

        target_dur = float(script.get("target_duration_sec", 30))
        logger.info(f"[{job_id}] Assembling {len(image_paths)} imgs | target={target_dur}s")

        work_dir  = os.path.join(settings.TEMP_DIR, f"asm_{job_id}")
        os.makedirs(work_dir, exist_ok=True)

        out_name   = f"{job_id}_{uuid.uuid4().hex[:6]}.mp4"
        out_path   = os.path.join(settings.OUTPUT_DIR, out_name)
        thumb_path = os.path.join(settings.OUTPUT_DIR, out_name.replace(".mp4", "_thumb.jpg"))

        try:
            # 1 — Audio duration
            audio_dur = await self._audio_duration(audio_path)

            # 2 — Trim if needed
            if target_dur > 5 and audio_dur > target_dur * 1.05:
                trimmed = os.path.join(work_dir, "audio_cut.mp3")
                await self._trim_audio(audio_path, trimmed, target_dur)
                audio_path = trimmed
                final_dur = target_dur
            else:
                final_dur = audio_dur

            # 3 — Scale each image + Ken Burns zoom effect
            videos = await self._images_to_clips(image_paths, work_dir, final_dur)

            # 4 — Concatenate clips
            concat_path = os.path.join(work_dir, "clips.txt")
            with open(concat_path, "w") as f:
                for v in videos:
                    f.write(f"file '{v}'\n")

            raw_video = os.path.join(work_dir, "raw.mp4")
            await self._concat_clips(concat_path, raw_video)

            # 5 — Generate Creashort-style ASS subtitles
            ass_path = os.path.join(work_dir, "subs.ass")
            self._make_creashort_ass(script, final_dur, ass_path)

            # 6 — Burn subtitles + merge audio
            await self._burn_subs(raw_video, audio_path, ass_path, out_path)

            # 7 — Thumbnail
            await self._thumbnail(out_path, thumb_path)

            size_mb = round(os.path.getsize(out_path) / 1024 / 1024, 2)
            logger.info(f"[{job_id}] ✓ {out_name} | {size_mb}MB | {final_dur:.1f}s")

            return {
                "video_path": out_path, "thumbnail_path": thumb_path,
                "duration_sec": round(final_dur, 2), "file_size_mb": size_mb,
                "filename": out_name,
            }
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _images_to_clips(self, image_paths: list, work_dir: str, total_dur: float) -> list:
        """
        Cada imagem → clip de vídeo com Ken Burns zoom suave.
        Creashort usa ~2-3s por imagem com movimento subtil.
        """
        clip_dur = total_dur / len(image_paths)
        # Min 2s, max 6s per clip for best effect
        clip_dur = max(2.0, min(clip_dur, 6.0))

        clips = []
        for i, src in enumerate(image_paths):
            dst = os.path.join(work_dir, f"clip_{i:03d}.mp4")

            # Scale image to correct size first
            scaled = os.path.join(work_dir, f"scaled_{i:03d}.jpg")
            await self._run([
                "ffmpeg", "-y", "-i", src,
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                "-q:v", "2", scaled
            ])

            # Ken Burns: alternating zoom in / zoom out
            # zoompan filter: slow zoom from 1.0 to 1.08 (subtle, Creashort style)
            n_frames = int(clip_dur * FPS)
            if i % 2 == 0:
                # Zoom in subtly
                zoom_filter = (
                    f"zoompan=z='min(zoom+0.0005,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    f":d={n_frames}:s={W}x{H}:fps={FPS}"
                )
            else:
                # Zoom out subtly  
                zoom_filter = (
                    f"zoompan=z='if(lte(zoom,1.0),1.08,max(1.0,zoom-0.0005))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    f":d={n_frames}:s={W}x{H}:fps={FPS}"
                )

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", scaled,
                "-vf", zoom_filter,
                "-t", str(clip_dur),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-pix_fmt", "yuv420p", "-an",
                "-threads", "1",
                dst
            ]
            await self._run(cmd)
            clips.append(dst)

        return clips

    async def _concat_clips(self, concat_path: str, out_path: str):
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_path,
            "-c", "copy", out_path
        ]
        await self._run(cmd)

    async def _burn_subs(self, video: str, audio: str, ass: str, out: str):
        """Burn ASS subtitles + merge audio."""
        ass_esc = ass.replace("\\", "/").replace(":", "\\:")
        cmd = [
            "ffmpeg", "-y",
            "-i", video,
            "-i", audio,
            "-vf", f"ass='{ass_esc}'",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart", "-pix_fmt", "yuv420p",
            "-threads", "1", "-shortest",
            out
        ]
        await self._run(cmd)

    def _make_creashort_ass(self, script: dict, total_dur: float, ass_path: str):
        """
        Gera legendas estilo Creashort em formato ASS:
        - 1-2 palavras por vez, centradas no ecrã
        - Fonte grande, bold, branca com sombra preta forte
        - Palavra por palavra em sincronia com o áudio
        - Posição: 70% do ecrã (não no fundo, não no centro)
        """

        # Recolher todo o texto
        parts = []
        hook = script.get("hook", {}).get("text", "")
        if hook:
            parts.append(hook)
        for seg in script.get("body", []):
            t = seg.get("text", "")
            if t:
                parts.append(t)
        cta = script.get("cta", {}).get("text", "")
        if cta:
            parts.append(cta)

        full_text = " ".join(parts)
        words = full_text.split()
        if not words:
            open(ass_path, "w").write(self._ass_header())
            return

        # Agrupar em chunks de 2 palavras (Creashort style)
        chunks = []
        i = 0
        while i < len(words):
            chunks.append(" ".join(words[i:i+2]))
            i += 2

        time_per_chunk = total_dur / max(len(chunks), 1)

        # Header ASS — define o estilo das legendas
        header = self._ass_header()
        events = []
        for idx, chunk in enumerate(chunks):
            start  = idx * time_per_chunk
            end    = start + time_per_chunk - 0.05
            # Uppercase para impacto visual (Creashort style)
            text   = chunk.upper()
            events.append(
                f"Dialogue: 0,{self._ts(start)},{self._ts(end)},"
                f"Creashort,,0,0,0,,{text}"
            )

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events) + "\n")

    def _ass_header(self) -> str:
        """
        ASS header com estilo Creashort:
        - Fonte grande (52px em 576p = equivalente a 90px em 1080p)
        - Bold, branca, sombra preta forte
        - Centrada horizontalmente, a 70% da altura
        - Sem caixa de fundo
        """
        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Creashort,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,3,2,2,20,20,{int(H * 0.28)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    @staticmethod
    def _ts(sec: float) -> str:
        """ASS timestamp format: H:MM:SS.cc"""
        h  = int(sec // 3600)
        m  = int((sec % 3600) // 60)
        s  = int(sec % 60)
        cs = int((sec % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    async def _trim_audio(self, src, dst, dur):
        await self._run(["ffmpeg", "-y", "-i", src, "-t", str(dur), "-c", "copy", dst])

    async def _thumbnail(self, video, thumb):
        try:
            await self._run(["ffmpeg", "-y", "-i", video, "-ss", "1", "-vframes", "1",
                             "-vf", f"scale={W//2}:{H//2}", "-q:v", "3", thumb])
        except Exception as e:
            logger.warning(f"Thumbnail failed: {e}")

    async def _audio_duration(self, path) -> float:
        out = await self._run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture=True
        )
        return float(json.loads(out)["format"]["duration"])

    async def _run(self, cmd, capture=False) -> str:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg error ({proc.returncode}):\n"
                f"CMD: {' '.join(cmd[:6])}...\n"
                f"STDERR: {stderr.decode()[-500:]}"
            )
        return stdout.decode() if capture else ""
