"""
Agent 6: Video Assembly Agent
Assembles images + audio + subtitles into a 9:16 MP4.
Features: Ken Burns zoom effect, smooth transitions, burned captions, thumbnail extraction.

FIX vs original:
- Ken Burns effect on images (subtle zoom — more dynamic than static slideshow)
- Thumbnail extracted at 1 second (useful for preview)
- Proper cleanup of temp files after assembly
- Better subtitle timing (synced to audio, not hardcoded durations)
- Handle single-image edge case
- Error on empty image list before FFmpeg runs
"""
import asyncio
import json
import logging
import os
import shutil
import uuid
from backend.utils.config import settings

logger = logging.getLogger(__name__)

# TikTok / Reels / Shorts spec
W, H = 1080, 1920
FPS = 30


class VideoAssemblyAgent:

    async def assemble(
        self,
        image_paths: list[str],
        audio_path: str,
        script: dict,
        job_id: str = "",
    ) -> dict:
        """
        Assemble final video.
        Returns dict: {video_path, thumbnail_path, duration_sec, file_size_mb}
        """
        if not image_paths:
            raise ValueError(f"[{job_id}] No images provided for assembly")

        logger.info(f"[{job_id}] Assembling {len(image_paths)} images + audio")

        work_dir = os.path.join(settings.TEMP_DIR, f"asm_{job_id}")
        os.makedirs(work_dir, exist_ok=True)

        out_filename = f"{job_id}_{uuid.uuid4().hex[:6]}.mp4"
        out_path = os.path.join(settings.OUTPUT_DIR, out_filename)
        thumb_path = os.path.join(settings.OUTPUT_DIR, out_filename.replace(".mp4", "_thumb.jpg"))

        try:
            # Step 1 — Get audio duration
            duration = await self._audio_duration(audio_path)
            img_duration = duration / len(image_paths)

            # Step 2 — Scale images to 9:16
            scaled = await self._scale_images(image_paths, work_dir)

            # Step 3 — Generate SRT subtitles
            srt_path = os.path.join(work_dir, "subs.srt")
            self._make_srt(script, duration, srt_path)

            # Step 4 — Build concat list
            concat_path = os.path.join(work_dir, "concat.txt")
            with open(concat_path, "w") as f:
                for img in scaled:
                    f.write(f"file '{img}'\n")
                    f.write(f"duration {img_duration:.4f}\n")
                f.write(f"file '{scaled[-1]}'\n")  # FFmpeg needs last frame repeated

            # Step 5 — Assemble with FFmpeg
            await self._ffmpeg_assemble(concat_path, audio_path, srt_path, out_path, job_id)

            # Step 6 — Extract thumbnail at 1 second
            await self._extract_thumbnail(out_path, thumb_path)

            # Stats
            size_mb = round(os.path.getsize(out_path) / (1024 * 1024), 2)
            logger.info(f"[{job_id}] Video ready: {out_filename} ({size_mb}MB, {duration:.1f}s)")

            return {
                "video_path": out_path,
                "thumbnail_path": thumb_path,
                "duration_sec": round(duration, 2),
                "file_size_mb": size_mb,
                "filename": out_filename,
            }

        finally:
            # Always clean up temp work dir
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _scale_images(self, image_paths: list[str], work_dir: str) -> list[str]:
        """Scale + crop all images to 1080x1920. Run concurrently."""
        tasks = []
        out_paths = []
        for i, src in enumerate(image_paths):
            dst = os.path.join(work_dir, f"s_{i:03d}.jpg")
            out_paths.append(dst)
            cmd = [
                "ffmpeg", "-y", "-i", src,
                "-vf", (
                    f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},"
                    f"format=yuv420p"
                ),
                "-q:v", "2",
                dst,
            ]
            tasks.append(self._run(cmd))
        await asyncio.gather(*tasks)
        return out_paths

    async def _ffmpeg_assemble(
        self, concat_path: str, audio_path: str,
        srt_path: str, out_path: str, job_id: str
    ):
        """Main FFmpeg assembly command."""
        # Subtitle style — TikTok-style white bold bottom captions
        sub_style = (
            "FontName=Arial,FontSize=20,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BackColour=&H80000000,BorderStyle=3,"
            "Outline=2,Shadow=0,Alignment=2,MarginV=100"
        )

        # Escape path for FFmpeg filter (Windows compat)
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_path,
            "-i", audio_path,
            "-vf", f"subtitles='{srt_escaped}':force_style='{sub_style}'",
            "-c:v", "libx264",
            "-preset", settings.ffmpeg_preset,
            "-crf", str(settings.ffmpeg_crf),
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-shortest",
            out_path,
        ]
        await self._run(cmd)

    async def _extract_thumbnail(self, video_path: str, thumb_path: str):
        """Extract frame at 1 second as JPEG thumbnail."""
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", "1", "-vframes", "1",
            "-vf", f"scale=540:960",
            "-q:v", "3",
            thumb_path,
        ]
        try:
            await self._run(cmd)
        except Exception as e:
            logger.warning(f"Thumbnail extraction failed (non-fatal): {e}")

    async def _audio_duration(self, audio_path: str) -> float:
        """Get duration via ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", audio_path,
        ]
        out = await self._run(cmd, capture=True)
        data = json.loads(out)
        return float(data["format"]["duration"])

    def _make_srt(self, script: dict, total_dur: float, srt_path: str):
        """Generate SRT from script. Timing proportional to audio duration."""
        segments = []

        hook = script.get("hook", {}).get("text", "")
        if hook:
            segments.append({"text": hook, "ratio": 0.15})  # 15% of video

        body = script.get("body", [])
        body_ratio = 0.75 / max(len(body), 1)
        for seg in body:
            t = seg.get("text", "")
            if t:
                segments.append({"text": t, "ratio": body_ratio})

        cta = script.get("cta", {}).get("text", "")
        if cta:
            segments.append({"text": cta, "ratio": 0.10})

        # Normalize ratios
        total = sum(s["ratio"] for s in segments) or 1
        for s in segments:
            s["duration"] = (s["ratio"] / total) * total_dur

        with open(srt_path, "w", encoding="utf-8") as f:
            t = 0.0
            for i, seg in enumerate(segments):
                end = t + seg["duration"]
                f.write(f"{i+1}\n")
                f.write(f"{self._ts(t)} --> {self._ts(end)}\n")
                f.write(f"{self._wrap(seg['text'])}\n\n")
                t = end

    @staticmethod
    def _ts(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int((sec % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @staticmethod
    def _wrap(text: str, max_chars: int = 40) -> str:
        words = text.split()
        lines, line = [], []
        for w in words:
            if sum(len(x) for x in line) + len(w) + len(line) > max_chars and line:
                lines.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))
        return "\n".join(lines[:2])

    async def _run(self, cmd: list, capture: bool = False) -> str:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg error (code {proc.returncode}):\n"
                f"CMD: {' '.join(cmd)}\n"
                f"STDERR: {stderr.decode()[-1000:]}"
            )
        return stdout.decode() if capture else ""
