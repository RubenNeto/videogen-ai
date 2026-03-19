"""
Pipeline Orchestrator — Video Generation
"""
import asyncio
import logging
import uuid
from datetime import datetime

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


class PipelineOrchestrator:

    def __init__(self):
        self.trend_agent     = TrendAnalysisAgent()
        self.strategy_agent  = ContentStrategyAgent()
        self.script_agent    = ScriptGenerationAgent()
        self.visual_agent    = VisualAgent()
        self.voiceover_agent = VoiceoverAgent()
        self.assembly_agent  = VideoAssemblyAgent()
        self.seo_agent       = SEOAgent()

    async def run(self, niche_id: str, niche_name: str, videos_count: int = None, job_id: str = None) -> str:
        """Entry point. Recebe job_id ja criado pela API."""
        if not job_id:
            job_id = str(uuid.uuid4())
            async with AsyncSessionLocal() as db:
                db.add(PipelineJob(
                    id=job_id, niche_id=niche_id, niche_name=niche_name,
                    status=JobStatus.RUNNING, progress_pct=0,
                ))
                await db.commit()

        count = videos_count or settings.VIDEOS_PER_RUN
        logger.info(f"[{job_id}] START niche='{niche_name}' videos={count}")

        try:
            # Stage 1: Trends
            await self._set_stage(job_id, AgentStage.TREND, 5)
            trends = await self._retry(job_id,
                self.trend_agent.analyze,
                niche=niche_name, job_id=job_id
            )
            await self._log(job_id, AgentStage.TREND, f"Found {len(trends.get('topics', []))} topics")
            await self._set_stage(job_id, AgentStage.TREND, 10)

            # Stage 2: Strategies
            await self._set_stage(job_id, AgentStage.STRATEGY, 12)
            strategies = await self._retry(job_id,
                self.strategy_agent.generate,
                trends=trends, count=count, job_id=job_id
            )
            await self._log(job_id, AgentStage.STRATEGY, f"Generated {len(strategies)} strategies")
            await self._set_stage(job_id, AgentStage.STRATEGY, 15)

            # Produce each video sequentially
            video_ids = []
            per_video_pct = 85 // count

            for idx, strategy in enumerate(strategies):
                base_pct = 15 + idx * per_video_pct
                try:
                    vid_id = await self._produce_video(
                        job_id, niche_id, niche_name,
                        strategy, idx, count, base_pct, per_video_pct
                    )
                    video_ids.append(vid_id)
                except Exception as e:
                    logger.error(f"[{job_id}] Video {idx+1} failed: {e}", exc_info=True)
                    await self._log(job_id, AgentStage.ASSEMBLY,
                                    f"Video {idx+1} failed: {str(e)[:200]}", level="ERROR")

            # Mark complete
            async with AsyncSessionLocal() as db:
                job = await db.get(PipelineJob, job_id)
                if job:
                    job.status = JobStatus.COMPLETED if video_ids else JobStatus.FAILED
                    job.progress_pct = 100
                    job.videos_count = len(video_ids)
                    job.completed_at = datetime.utcnow()
                    await db.commit()

            logger.info(f"[{job_id}] DONE {len(video_ids)}/{count} videos")
            return job_id

        except Exception as e:
            logger.error(f"[{job_id}] FATAL: {e}", exc_info=True)
            async with AsyncSessionLocal() as db:
                job = await db.get(PipelineJob, job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)[:500]
                    await db.commit()
            raise

    async def _produce_video(
        self, job_id, niche_id, niche_name,
        strategy, idx, total, base_pct, pct_budget
    ) -> str:
        video_id = str(uuid.uuid4())
        logger.info(f"[{job_id}] Video {idx+1}/{total}: {strategy.get('topic','?')}")

        async with AsyncSessionLocal() as db:
            db.add(Video(
                id=video_id, job_id=job_id,
                niche_id=niche_id, niche_name=niche_name,
                status=JobStatus.RUNNING,
            ))
            await db.commit()

        step = max(pct_budget // 5, 1)

        # Script
        await self._set_stage(job_id, AgentStage.SCRIPT, base_pct + step)
        script = await self._retry(job_id,
            self.script_agent.generate,
            strategy=strategy, job_id=job_id
        )
        await self._log(job_id, AgentStage.SCRIPT,
                        f"[{idx+1}] Hook: \"{script.get('hook', {}).get('text', '')[:50]}\"")

        # Images
        await self._set_stage(job_id, AgentStage.VISUAL, base_pct + step * 2)
        image_paths = await self._retry(job_id,
            self.visual_agent.generate,
            script=script, job_id=job_id
        )
        await self._log(job_id, AgentStage.VISUAL, f"[{idx+1}] {len(image_paths)} images ready")

        # Voiceover
        await self._set_stage(job_id, AgentStage.VOICEOVER, base_pct + step * 3)
        audio_path = await self._retry(job_id,
            self.voiceover_agent.generate,
            script=script, job_id=job_id
        )
        await self._log(job_id, AgentStage.VOICEOVER, f"[{idx+1}] Audio ready")

        # Assembly
        await self._set_stage(job_id, AgentStage.ASSEMBLY, base_pct + step * 4)
        result = await self._retry(job_id,
            self.assembly_agent.assemble,
            image_paths=image_paths,
            audio_path=audio_path,
            script=script,
            job_id=job_id
        )
        await self._log(job_id, AgentStage.ASSEMBLY,
                        f"[{idx+1}] {result['filename']} ({result['file_size_mb']}MB)")

        # SEO
        await self._set_stage(job_id, AgentStage.SEO, base_pct + step * 4 + step // 2)
        seo = await self._retry(job_id,
            self.seo_agent.generate,
            strategy=strategy, script=script, job_id=job_id
        )
        await self._log(job_id, AgentStage.SEO, f"[{idx+1}] \"{seo.get('title', '')[:50]}\"")

        # S3 (optional)
        s3_url = None
        if settings.has_s3:
            try:
                from backend.utils.storage import upload_to_s3
                s3_url = await upload_to_s3(result["video_path"], f"videos/{video_id}.mp4")
            except Exception as e:
                logger.warning(f"[{job_id}] S3 skip: {e}")

        # Save to DB
        async with AsyncSessionLocal() as db:
            video = await db.get(Video, video_id)
            if video:
                video.title        = seo.get("title", "")
                video.script       = script.get("full_script", "")
                video.hook         = script.get("hook", {}).get("text", "")
                video.caption      = seo.get("caption", "")
                video.hashtags     = seo.get("hashtags", [])
                video.local_path   = result["video_path"]
                video.thumbnail    = result.get("thumbnail_path")
                video.s3_url       = s3_url
                video.file_size_mb = result["file_size_mb"]
                video.duration_sec = result["duration_sec"]
                video.image_source = "pexels" if settings.has_pexels else "dalle"
                video.status       = JobStatus.COMPLETED
                video.completed_at = datetime.utcnow()
                await db.commit()

        return video_id

    async def _retry(self, _jid: str, func, *args, **kwargs):
        """
        Retry wrapper.
        Assinatura: _retry(job_id, func, *args, **kwargs)
        job_id e func sao positional — kwargs sao passados ao func.
        """
        for attempt in range(settings.MAX_RETRIES):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if attempt == settings.MAX_RETRIES - 1:
                    raise
                wait = settings.RETRY_DELAY_SECONDS * (attempt + 1)
                logger.warning(f"[{_jid}] Attempt {attempt+1} failed: {e}. Retry in {wait}s...")
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
            db.add(AgentLog(
                job_id=job_id, stage=stage.value,
                level=level, message=message
            ))
            await db.commit()
        logger.info(f"[{job_id}][{stage.value}] {message}")
