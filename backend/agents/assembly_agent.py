"""
Agent 6: Video Assembly — Creashort style
FIXES:
- Ken Burns substituído por scale simples + fade (zoompan crashava no Railway)
- Duração respeitada: imagens duram o tempo do audio real
- ASS subtitles estilo Creashort (maiúsculas, centradas, bold)
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
        logger.info(f"[{job_id}] Assembly: {len(image_paths)} images | target={target_dur}s")

        work_dir   = os.path.join(settings.TEMP_DIR, f"asm_{job_id}")
        os.makedirs(work_dir, exist_ok=True)
        out_name   = f"{job_id}_{uuid.uuid4().hex[:6]}.mp4"
        out_path   = os.path.join(settings.OUTPUT_DIR, out_name)
        thumb_path = os.path.join(settings.OUTPUT_DIR, out_name.replace(".mp4", "_thumb.jpg"))

        try:
            # 1 — Real audio duration
            audio_dur = await self._audio_duration(audio_path)
            logger.info(f"[{job_id}] Audio duration: {audio_dur:.1f}s (target: {target_dur:.1f}s)")

            # 2 — Match audio to target duration
            if target_dur > 5:
                adjusted = os.path.join(work_dir, "audio_adj.mp3")
                await self._adjust_audio(audio_path, adjusted, audio_dur, target_dur)
                audio_path = adjusted
                final_dur  = target_dur
                logger.info(f"[{job_id}] Audio adjusted {audio_dur:.1f}s -> {target_dur:.1f}s")
            else:
                final_dur = audio_dur

            # 3 — Scale images (simple, fast, no zoom effects)
            scaled = await self._scale_images(image_paths, work_dir)

            # 4 — Build video from images timed to audio
            img_dur = final_dur / len(scaled)
            concat_path = os.path.join(work_dir, "concat.txt")
            with open(concat_path, "w") as f:
                for img in scaled:
                    f.write(f"file '{img}'\nduration {img_dur:.4f}\n")
                # FFmpeg needs last frame repeated
                f.write(f"file '{scaled[-1]}'\n")

            # 5 — Generate Creashort-style ASS subtitles
            ass_path = os.path.join(work_dir, "subs.ass")
            self._make_ass(script, final_dur, ass_path)

            # 6 — Assemble: images + audio + subtitles
            await self._assemble(concat_path, audio_path, ass_path, out_path)

            # 7 — Thumbnail
            await self._thumbnail(out_path, thumb_path)

            size_mb = round(os.path.getsize(out_path) / 1024 / 1024, 2)
            logger.info(f"[{job_id}] ✓ {out_name} | {size_mb}MB | {final_dur:.1f}s")

            return {
                "video_path":     out_path,
                "thumbnail_path": thumb_path,
                "duration_sec":   round(final_dur, 2),
                "file_size_mb":   size_mb,
                "filename":       out_name,
            }
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _scale_images(self, paths: list, work_dir: str) -> list:
        """Scale + crop images to 576x1024. Simple and fast."""
        out = []
        for i, src in enumerate(paths):
            dst = os.path.join(work_dir, f"img{i:03d}.jpg")
            cmd = [
                "ffmpeg", "-y", "-i", src,
                "-vf", (
                    f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},"
                    f"format=yuv420p"
                ),
                "-q:v", "2", "-threads", "1", dst
            ]
            await self._run(cmd)
            out.append(dst)
            logger.debug(f"[scaled] img {i+1}/{len(paths)}")
        return out

    async def _assemble(self, concat: str, audio: str, ass: str, out: str):
        """Concat images + burn ASS subs + merge audio."""
        ass_esc = ass.replace("\\", "/").replace(":", "\\:")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat,
            "-i", audio,
            "-vf", f"ass='{ass_esc}'",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-threads", "1", "-shortest",
            out
        ]
        await self._run(cmd)

    def _make_ass(self, script: dict, total_dur: float, ass_path: str):
        """
        ASS subtitles — Creashort style:
        - UPPERCASE, bold, centrado
        - 2 palavras por chunk, ritmo rápido
        - Fonte grande (52px em 576p)
        - Sombra forte, sem caixa
        """
        # Collect all spoken text
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

        full = " ".join(parts).strip()
        # Fallback: use full_script if body is empty
        if not full:
            full = script.get("full_script", "")

        words = full.split()
        if not words:
            open(ass_path, "w").write(self._ass_header())
            return

        # 2 words per subtitle chunk
        chunks = [" ".join(words[i:i+2]) for i in range(0, len(words), 2)]
        chunk_dur = total_dur / max(len(chunks), 1)

        header = self._ass_header()
        events = []
        for i, chunk in enumerate(chunks):
            start = i * chunk_dur
            end   = start + chunk_dur - 0.04
            text  = chunk.upper()
            events.append(
                f"Dialogue: 0,{self._ts(start)},{self._ts(end)},"
                f"Main,,0,0,0,,{text}"
            )

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("\n".join(events) + "\n")

    def _ass_header(self) -> str:
        # MarginV = distance from bottom (in px at PlayResY=1024)
        # 290 places text at ~72% from top (Creashort position)
        return (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            f"PlayResX: {W}\n"
            f"PlayResY: {H}\n"
            "ScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Main,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
            "-1,0,0,0,100,100,2,0,1,3,3,2,20,20,290,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

    @staticmethod
    def _ts(sec: float) -> str:
        """ASS format: H:MM:SS.cc"""
        h  = int(sec // 3600)
        m  = int((sec % 3600) // 60)
        s  = int(sec % 60)
        cs = int((sec % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    async def _adjust_audio(self, src: str, dst: str, actual_dur: float, target_dur: float):
        """
        Adjust audio to match target duration:
        - If audio is longer: trim it
        - If audio is shorter: loop it to fill the target duration
        """
        if actual_dur > target_dur * 1.02:
            # Trim
            await self._trim_audio(src, dst, target_dur)
        elif actual_dur < target_dur * 0.9:
            # Loop: repeat audio to fill target duration
            # Use FFmpeg aloop filter
            loops = int(target_dur / actual_dur) + 1
            cmd = [
                "ffmpeg", "-y", "-i", src,
                "-filter_complex", f"aloop=loop={loops}:size=2e+09,atrim=duration={target_dur}",
                "-q:a", "2", dst
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, err = await proc.communicate()
            if proc.returncode != 0:
                logger.warning(f"Audio loop failed: {err.decode()[-200:]}, using original")
                import shutil
                shutil.copy(src, dst)
        else:
            # Close enough, just copy
            import shutil
            shutil.copy(src, dst)

    async def _trim_audio(self, src, dst, dur):
        await self._run(["ffmpeg", "-y", "-i", src, "-t", str(dur), "-c", "copy", dst])

    async def _thumbnail(self, video, thumb):
        try:
            await self._run([
                "ffmpeg", "-y", "-i", video,
                "-ss", "1", "-vframes", "1",
                "-vf", f"scale={W//2}:{H//2}",
                "-q:v", "3", thumb
            ])
        except Exception as e:
            logger.warning(f"Thumbnail skip: {e}")

    async def _audio_duration(self, path) -> float:
        out  = await self._run(
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
            err = stderr.decode()[-600:]
            raise RuntimeError(
                f"FFmpeg error ({proc.returncode}):\n"
                f"CMD: {' '.join(cmd[:6])}...\n"
                f"STDERR: {err}"
            )
        return stdout.decode() if capture else ""
