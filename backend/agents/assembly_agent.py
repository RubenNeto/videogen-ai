"""
Agent 6: Video Assembly Agent
- Resolucao 1080x1920 (qualidade original)
- Duracao respeitada: audio e cortado/padded para bater certo com o target
- Imagens processadas uma a uma (low RAM)
- ultrafast preset, 1 thread
"""
import asyncio
import json
import logging
import os
import shutil
import uuid
from backend.utils.config import settings

logger = logging.getLogger(__name__)

W, H = 1080, 1920
FPS  = 30


class VideoAssemblyAgent:

    async def assemble(
        self,
        image_paths: list[str],
        audio_path: str,
        script: dict,
        job_id: str = "",
    ) -> dict:
        if not image_paths:
            raise ValueError(f"[{job_id}] No images")

        # Duracao alvo (do script ou fallback para audio real)
        target_dur = float(script.get("target_duration_sec", 0))

        logger.info(f"[{job_id}] Assembling {len(image_paths)} images @ {W}x{H}")

        work_dir = os.path.join(settings.TEMP_DIR, f"asm_{job_id}")
        os.makedirs(work_dir, exist_ok=True)

        out_filename = f"{job_id}_{uuid.uuid4().hex[:6]}.mp4"
        out_path     = os.path.join(settings.OUTPUT_DIR, out_filename)
        thumb_path   = os.path.join(settings.OUTPUT_DIR, out_filename.replace(".mp4", "_thumb.jpg"))

        try:
            # 1 - Duracao real do audio
            audio_dur = await self._audio_duration(audio_path)

            # Se target_dur foi definido e audio e mais curto, usa audio_dur
            # (nao fazemos loop de audio — so garantimos que o video nao fica maior)
            final_dur = audio_dur
            if target_dur > 0 and audio_dur > target_dur:
                # Cortar audio para bater com target
                trimmed_audio = os.path.join(work_dir, "audio_trimmed.mp3")
                await self._trim_audio(audio_path, trimmed_audio, target_dur)
                audio_path = trimmed_audio
                final_dur  = target_dur
                logger.info(f"[{job_id}] Audio trimmed to {target_dur}s")

            img_duration = final_dur / len(image_paths)

            # 2 - Escalar imagens (uma a uma, menos RAM)
            scaled = await self._scale_images_sequential(image_paths, work_dir)

            # 3 - SRT
            srt_path = os.path.join(work_dir, "subs.srt")
            self._make_srt(script, final_dur, srt_path)

            # 4 - Concat list
            concat_path = os.path.join(work_dir, "concat.txt")
            with open(concat_path, "w") as f:
                for img in scaled:
                    f.write(f"file '{img}'\n")
                    f.write(f"duration {img_duration:.4f}\n")
                f.write(f"file '{scaled[-1]}'\n")

            # 5 - Montar video
            await self._ffmpeg_assemble(concat_path, audio_path, srt_path, out_path, job_id)

            # 6 - Thumbnail
            await self._extract_thumbnail(out_path, thumb_path)

            size_mb = round(os.path.getsize(out_path) / (1024 * 1024), 2)
            logger.info(f"[{job_id}] Done: {out_filename} ({size_mb}MB, {final_dur:.1f}s)")

            return {
                "video_path":     out_path,
                "thumbnail_path": thumb_path,
                "duration_sec":   round(final_dur, 2),
                "file_size_mb":   size_mb,
                "filename":       out_filename,
            }

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    async def _trim_audio(self, src: str, dst: str, duration: float):
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-t", str(duration),
            "-c", "copy",
            dst,
        ]
        await self._run(cmd)

    async def _scale_images_sequential(self, image_paths: list, work_dir: str) -> list:
        """Uma a uma para minimizar RAM."""
        out_paths = []
        for i, src in enumerate(image_paths):
            dst = os.path.join(work_dir, f"s_{i:03d}.jpg")
            cmd = [
                "ffmpeg", "-y", "-i", src,
                "-vf", (
                    f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},"
                    f"format=yuv420p"
                ),
                "-q:v", "3",
                "-threads", "1",
                dst,
            ]
            await self._run(cmd)
            out_paths.append(dst)
        return out_paths

    async def _ffmpeg_assemble(
        self, concat_path, audio_path, srt_path, out_path, job_id
    ):
        sub_style = (
            "FontName=Arial,FontSize=20,Bold=1,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=3,Outline=2,Shadow=0,Alignment=2,MarginV=100"
        )
        srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_path,
            "-i", audio_path,
            "-vf", f"subtitles='{srt_escaped}':force_style='{sub_style}'",
            "-c:v", "libx264",
            "-preset", "ultrafast",   # menos RAM
            "-crf", "26",
            "-threads", "1",          # menos RAM
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-shortest",
            out_path,
        ]
        await self._run(cmd)

    async def _extract_thumbnail(self, video_path, thumb_path):
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", "1", "-vframes", "1",
            "-vf", "scale=540:960",
            "-q:v", "4",
            thumb_path,
        ]
        try:
            await self._run(cmd)
        except Exception as e:
            logger.warning(f"Thumbnail failed (non-fatal): {e}")

    async def _audio_duration(self, audio_path: str) -> float:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", audio_path,
        ]
        out  = await self._run(cmd, capture=True)
        data = json.loads(out)
        return float(data["format"]["duration"])

    def _make_srt(self, script: dict, total_dur: float, srt_path: str):
        segments = []
        hook = script.get("hook", {}).get("text", "")
        if hook:
            segments.append({"text": hook, "ratio": 0.15})
        body_ratio = 0.75 / max(len(script.get("body", [])), 1)
        for seg in script.get("body", []):
            t = seg.get("text", "")
            if t:
                segments.append({"text": t, "ratio": body_ratio})
        cta = script.get("cta", {}).get("text", "")
        if cta:
            segments.append({"text": cta, "ratio": 0.10})

        total = sum(s["ratio"] for s in segments) or 1
        for s in segments:
            s["duration"] = (s["ratio"] / total) * total_dur

        with open(srt_path, "w", encoding="utf-8") as f:
            t = 0.0
            for i, seg in enumerate(segments):
                end = t + seg["duration"]
                f.write(f"{i+1}\n{self._ts(t)} --> {self._ts(end)}\n{self._wrap(seg['text'])}\n\n")
                t = end

    @staticmethod
    def _ts(sec: float) -> str:
        h  = int(sec // 3600)
        m  = int((sec % 3600) // 60)
        s  = int(sec % 60)
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
                f"CMD: {' '.join(cmd[:8])}...\n"
                f"STDERR: {stderr.decode()[-800:]}"
            )
        return stdout.decode() if capture else ""
