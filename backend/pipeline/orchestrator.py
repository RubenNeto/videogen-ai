"""
Pipeline Orchestrator — Video Generation Focus
Coordinates 7 agents to produce download-ready MP4 videos.
No TikTok publishing — user downloads and posts manually.

Key improvements vs original:
- Sequential per-video (avoids API rate limits from concurrent DALL·E calls)
- Progress percentage tracked in DB (0-100)
- Proper error isolation per video (one failure doesn't kill all 3)
- Temp files cleaned up automatically
- Local file path stored — no S3 dependency
- S3 upload is optional bonus
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from backend.agents.trend_agent import TrendAnalysisAgent
from backend.agents.strategy_agent import ContentStrategyAgent
from backend.agents.script_agent import ScriptGenerationAgent
from backend.agents.visual_agent import VisualAgent
from backend.agents.voiceover_agent import VoiceoverAgent
from backend.agents.assembly_agent import VideoAssemblyAgent
from backend.agents.seo_agent import SEOAgent
from backend.utils.database import (
    AsyncSessionLocal, PipelineJob, Video, AgentLog,
    JobStatus, AgentStage
)
from backend.utils.config import settings

logger = logging.getLogger(__name__)

# Stage weights for progress calculation (must sum to 100)
STAGE_WEIGHTS = {
    AgentStage.TREND:     10,
    AgentStage.STRATEGY:  5,
    AgentStage.SCRIPT:    10,
    AgentStage.VISUAL:    35,  # Heaviest — image generation
    AgentStage.VOICEOVER: 20,
    AgentStage.ASSEMBLY:  15,
    AgentStage.SEO:       5,
}


class PipelineOrchestrator:

    def __init__(self):
        self.trend_agent    = TrendAnalysisAgent()
        self.strategy_agent = ContentStrategyAgent()
        self.script_agent   = ScriptGenerationAgent()
        self.visual_agent   = VisualAgent()
        self.voiceover_agent = VoiceoverAgent()
        self.assembly_agent = VideoAssemblyAgent()
        self.seo_agent      = SEOAgent()

    async def run(self, niche_id: str, niche_name: str, videos_count: int = None, job_id: str = None) -> str:
        """Entry point. Usa o job_id existente criado pela API (não cria um novo)."""
        if not job_id:
            # fallback se chamado directamente
            job_id = str(uuid.uuid4())
            async with AsyncSessionLocal() as db:
                job = PipelineJob(
                    id=job_id,
                    niche_id=niche_id,
                    niche_name=niche_name,
                    status=JobStatus.RUNNING,
                    progress_pct=0,
                )
                db.add(job)
                await db.commit()

        count = videos_count or settings.VIDEOS_PER_RUN
        logger.info(f"[Job {job_id}] START — niche='{niche_name}', videos={count}")

        try:
            # ─ Stage 1: Trends ───────────────────────────────────────────
            await self._set_stage(job_id, AgentStage.TREND, 5)
            trends = await self._retry(
                self.trend_agent.analyze, job_id,
                niche=niche_name, job_id=job_id
            )
            await self._log(job_id, AgentStage.TREND, f"Found {len(trends.get('topics',[]))} trending topics")
            await self._set_stage(job_id, AgentStage.TREND, 10)

            # ─ Stage 2: Strategies ───────────────────────────────────────
            await self._set_stage(job_id, AgentStage.STRATEGY, 12)
            strategies = await self._retry(
                self.strategy_agent.generate, job_id,
                trends=trends, count=count, job_id=job_id
            )
            await self._log(job_id, AgentStage.STRATEGY, f"Generated {len(strategies)} video strategies")
            await self._set_stage(job_id, AgentStage.STRATEGY, 15)

            # ─ Produce videos SEQUENTIALLY (avoid API rate limits) ───────
            video_ids = []
            per_video_progress = 85 // count  # Divide remaining 85% across videos

            for idx, strategy in enumerate(strategies):
                base_pct = 15 + idx * per_video_progress
                try:
                    vid_id = await self._produce_video(
                        job_id, niche_id, niche_name,
                        strategy, idx, count,
                        base_pct, per_video_progress
                    )
                    video_ids.append(vid_id)
                except Exception as e:
                    logger.error(f"[Job {job_id}] Video {idx+1} failed: {e}", exc_info=True)
                    await self._log(job_id, AgentStage.ASSEMBLY, f"Video {idx+1} failed: {str(e)[:200]}", level="ERROR")
                    # Continue with next video — don't abort entire job

            # ─ Complete ──────────────────────────────────────────────────
            async with AsyncSessionLocal() as db:
                job = await db.get(PipelineJob, job_id)
                job.status = JobStatus.COMPLETED if video_ids else JobStatus.FAILED
                job.progress_pct = 100
                job.videos_count = len(video_ids)
                job.completed_at = datetime.utcnow()
                await db.commit()

            logger.info(f"[Job {job_id}] DONE — {len(video_ids)}/{count} videos generated")
            return job_id

        except Exception as e:
            logger.error(f"[Job {job_id}] FATAL: {e}", exc_info=True)
            async with AsyncSessionLocal() as db:
                job = await db.get(PipelineJob, job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)[:500]
                    await db.commit()
            raise

    async def _produce_video(
        self,
        job_id: str, niche_id: str, niche_name: str,
        strategy: dict, idx: int, total: int,
        base_pct: int, pct_budget: int,
    ) -> str:
        video_id = str(uuid.uuid4())
        logger.info(f"[Job {job_id}] Video {idx+1}/{total}: {strategy.get('topic','?')}")

        async with AsyncSessionLocal() as db:
            video = Video(
                id=video_id,
                job_id=job_id,
                niche_id=niche_id,
                niche_name=niche_name,
                status=JobStatus.RUNNING,
            )
            db.add(video)
            await db.commit()

        step = pct_budget // 5  # 5 steps within this video's budget

        # Script
        await self._set_stage(job_id, AgentStage.SCRIPT, base_pct + step)
        script = await self._retry(
            self.script_agent.generate, job_id,
            strategy=strategy, job_id=job_id
        )
        await self._log(job_id, AgentStage.SCRIPT, f"[{idx+1}] Script: \"{script.get('hook',{}).get('text','')[:50]}\"")

        # Images
        await self._set_stage(job_id, AgentStage.VISUAL, base_pct + step * 2)
        image_paths = await self._retry(
            self.visual_agent.generate, job_id,
            script=script, job_id=job_id
        )
        await self._log(job_id, AgentStage.VISUAL, f"[{idx+1}] {len(image_paths)} images ready")

        # Voiceover
        await self._set_stage(job_id, AgentStage.VOICEOVER, base_pct + step * 3)
        audio_path = await self._retry(
            self.voiceover_agent.generate, job_id,
            script=script, job_id=job_id
        )
        await self._log(job_id, AgentStage.VOICEOVER, f"[{idx+1}] Audio ready")

        # Assembly
        await self._set_stage(job_id, AgentStage.ASSEMBLY, base_pct + step * 4)
        result = await self._retry(
            self.assembly_agent.assemble, job_id,
            image_paths=image_paths,
            audio_path=audio_path,
            script=script,
            job_id=job_id,
        )
        await self._log(job_id, AgentStage.ASSEMBLY, f"[{idx+1}] Video: {result['filename']} ({result['file_size_mb']}MB)")

        # SEO/Caption
        await self._set_stage(job_id, AgentStage.SEO, base_pct + step * 4 + step // 2)
        seo = await self._retry(
            self.seo_agent.generate, job_id,
            strategy=strategy, script=script, job_id=job_id
        )
        await self._log(job_id, AgentStage.SEO, f"[{idx+1}] Caption: \"{seo.get('title','')[:50]}\"")

        # Optional S3 upload
        s3_url = None
        if settings.has_s3:
            try:
                from backend.utils.storage import upload_to_s3
                s3_url = await upload_to_s3(result["video_path"], f"videos/{video_id}.mp4")
            except Exception as e:
                logger.warning(f"[{job_id}] S3 upload failed (non-fatal): {e}")

        # Save to DB
        async with AsyncSessionLocal() as db:
            video = await db.get(Video, video_id)
            video.title       = seo.get("title", "")
            video.script      = script.get("full_script", "")
            video.hook        = script.get("hook", {}).get("text", "")
            video.caption     = seo.get("caption", "")
            video.hashtags    = seo.get("hashtags", [])
            video.local_path  = result["video_path"]
            video.thumbnail   = result.get("thumbnail_path")
            video.s3_url      = s3_url
            video.file_size_mb = result["file_size_mb"]
            video.duration_sec = result["duration_sec"]
            video.image_source = "pexels" if settings.has_pexels else "dalle"
            video.status      = JobStatus.COMPLETED
            video.completed_at = datetime.utcnow()
            await db.commit()

        return video_id

    async def _retry(self, func, job_id: str, *args, **kwargs):
        for attempt in range(settings.MAX_RETRIES):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if attempt == settings.MAX_RETRIES - 1:
                    raise
                wait = settings.RETRY_DELAY_SECONDS * (attempt + 1)
                logger.warning(f"[{job_id}] Attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)

    async def _set_stage(self, job_id: str, stage: AgentStage, pct: int):
        async with AsyncSessionLocal() as db:
            job = await db.get(PipelineJob, job_id)
            if job:
                job.current_stage = stage
                job.progress_pct = min(pct, 99)
                await db.commit()

    async def _log(self, job_id: str, stage: AgentStage, message: str, level: str = "INFO"):
        async with AsyncSessionLocal() as db:
            db.add(AgentLog(job_id=job_id, stage=stage.value, level=level, message=message))
            await db.commit()
        logger.info(f"[{job_id}][{stage.value}] {message}")
