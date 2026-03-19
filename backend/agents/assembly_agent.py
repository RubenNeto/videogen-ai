"""
Agent 6: Video Assembly Agent
- Resolucao 576x1024 (igual ao video de referencia, menos RAM)
- Legendas word-by-word estilo karaoke (como o video de referencia)
- Duracao respeitada via trim do audio
- ultrafast, 1 thread
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
FPS  = 24   # igual ao video de referencia


class VideoAssemblyAgent:

    async def assemble(self, image_paths, audio_path, script, job_id="") -> dict:
        if not image_paths:
            raise ValueError(f"[{job_id}] No images")

        target_dur = float(script.get("target_duration_sec", 0))
        logger.info(f"[{job_id}] Assembling {len(image_paths)} imgs @ {W}x{H} target={target_dur}s")

        work_dir = os.path.join(settings.TEMP_DIR, f"asm_{job_id}")
        os.makedirs(work_dir, exist_ok=True)

        out_name  = f"{job_id}_{uuid.uuid4().hex[:6]}.mp4"
        out_path  = os.path.join(settings.OUTPUT_DIR, out_name)
        thumb_path = os.path.join(settings.OUTPUT_DIR, out_name.replace(".mp4", "_thumb.jpg"))

        try:
            # 1 — Get real audio duration
            audio_dur = await self._audio_duration(audio_path)

            # 2 — Trim audio if target is shorter
            if target_dur > 5 and audio_dur > target_dur * 1.1:
                trimmed = os.path.join(work_dir, "audio_cut.mp3")
                await self._trim_audio(audio_path, trimmed, target_dur)
                audio_path = trimmed
                final_dur = target_dur
                logger.info(f"[{job_id}] Audio trimmed {audio_dur:.1f}s -> {target_dur:.1f}s")
            else:
                final_dur = audio_dur

            img_dur = final_dur / len(image_paths)

            # 3 — Scale images (one by one)
            scaled = await self._scale_images(image_paths, work_dir)

            # 4 — Word-by-word SRT (karaoke style like reference video)
            srt_path = os.path.join(work_dir, "subs.srt")
            self._make_word_srt(script, final_dur, srt_path)

            # 5 — Concat list
            concat = os.path.join(work_dir, "concat.txt")
            with open(concat, "w") as f:
                for img in scaled:
                    f.write(f"file '{img}'\nduration {img_dur:.4f}\n")
                f.write(f"file '{scaled[-1]}'\n")

            # 6 — Assemble
            await self._assemble(concat, audio_path, srt_path, out_path)

            # 7 — Thumbnail
            await self._thumbnail(out_path, thumb_path)

            size_mb = round(os.path.getsize(out_path) / 1024 / 1024, 2)
            logger.info(f"[{job_id}] Done: {out_name} {size_mb}MB {final_dur:.1f}s")

            return {
                "video_path": out_path, "thumbnail_path": thumb_path,
                "duration_sec": round(final_dur, 2), "file_size_mb": size_mb,
                "filename": out_name,
            }
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _scale_images(self, paths, work_dir):
        out = []
        for i, src in enumerate(paths):
            dst = os.path.join(work_dir, f"s{i:03d}.jpg")
            cmd = ["ffmpeg", "-y", "-i", src,
                   "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},format=yuv420p",
                   "-q:v", "3", "-threads", "1", dst]
            await self._run(cmd)
            out.append(dst)
        return out

    async def _assemble(self, concat, audio, srt, out):
        # Subtitle style matching reference video:
        # - Small font, white, centered, 70% down screen
        # - Black outline, no background box
        srt_esc = srt.replace("\\", "/").replace(":", "\\:")
        sub_style = (
            "FontName=Arial,FontSize=11,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=1,Outline=1,Shadow=0,"
            "Alignment=2,MarginV=60"
        )
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat,
            "-i", audio,
            "-vf", f"subtitles='{srt_esc}':force_style='{sub_style}'",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-threads", "1",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-shortest", out,
        ]
        await self._run(cmd)

    def _make_word_srt(self, script, total_dur, srt_path):
        """
        Word-by-word karaoke subtitles — each entry shows 2-3 words max.
        Matches the reference video style exactly.
        """
        # Collect all text
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
            # Fallback empty SRT
            with open(srt_path, "w") as f:
                f.write("")
            return

        # Distribute words evenly across duration
        # Group into chunks of 2-3 words
        chunks = []
        i = 0
        while i < len(words):
            # 2 words per chunk (matches reference video)
            chunk = " ".join(words[i:i+2])
            chunks.append(chunk)
            i += 2

        time_per_chunk = total_dur / max(len(chunks), 1)

        with open(srt_path, "w", encoding="utf-8") as f:
            for idx, chunk in enumerate(chunks):
                start = idx * time_per_chunk
                end   = start + time_per_chunk - 0.05  # small gap between words
                f.write(f"{idx+1}\n{self._ts(start)} --> {self._ts(end)}\n{chunk}\n\n")

    async def _trim_audio(self, src, dst, dur):
        cmd = ["ffmpeg", "-y", "-i", src, "-t", str(dur), "-c", "copy", dst]
        await self._run(cmd)

    async def _thumbnail(self, video, thumb):
        try:
            cmd = ["ffmpeg", "-y", "-i", video, "-ss", "1", "-vframes", "1",
                   "-vf", f"scale={W//2}:{H//2}", "-q:v", "4", thumb]
            await self._run(cmd)
        except Exception as e:
            logger.warning(f"Thumbnail failed: {e}")

    async def _audio_duration(self, path) -> float:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
        out = await self._run(cmd, capture=True)
        return float(json.loads(out)["format"]["duration"])

    @staticmethod
    def _ts(sec: float) -> str:
        h = int(sec // 3600); m = int((sec % 3600) // 60)
        s = int(sec % 60);    ms = int((sec % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    async def _run(self, cmd, capture=False) -> str:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg error (code {proc.returncode}):\n"
                f"CMD: {' '.join(cmd[:6])}...\n"
                f"STDERR: {stderr.decode()[-600:]}"
            )
        return stdout.decode() if capture else ""
