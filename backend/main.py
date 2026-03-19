"""
VideoGen AI — FastAPI Backend
All routes in one file for simplicity.
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import asyncio
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.config import settings
from backend.utils.database import (
    init_db, get_db,
    Niche, PipelineJob, Video, AgentLog,
    JobStatus, AgentStage
)
from backend.pipeline.orchestrator import PipelineOrchestrator

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("VideoGen AI starting...")
    await init_db()
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    os.makedirs(settings.TEMP_DIR, exist_ok=True)
    yield
    logger.info("VideoGen AI stopping...")


app = FastAPI(
    title="VideoGen AI",
    version="2.0.0",
    description="AI video generation pipeline — generate & download TikTok-ready videos",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated videos
if os.path.exists(settings.OUTPUT_DIR):
    app.mount("/videos", StaticFiles(directory=settings.OUTPUT_DIR), name="videos")

# Serve frontend (SPA) — Railway doesn't need nginx this way
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(_FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static_assets")


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    from backend.utils.ai_client import get_provider_name
    return {
        "status": "ok",
        "version": "2.0.0",
        "ai_provider": settings.ai_provider,
        "ai_provider_name": get_provider_name(),
        "has_ai": settings.has_any_ai,
        "services": {
            "groq": bool(settings.GROQ_API_KEY),
            "gemini": bool(settings.GEMINI_API_KEY),
            "openai": bool(settings.OPENAI_API_KEY),
            "elevenlabs": settings.has_elevenlabs,
            "pexels": settings.has_pexels,
            "gtts_fallback": True,
            "s3": settings.has_s3,
        }
    }


# ─── Niches ───────────────────────────────────────────────────────────────────

class NicheCreate(BaseModel):
    name: str
    description: str = ""


@app.get("/api/niches")
async def list_niches(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Niche).where(Niche.is_active == True).order_by(Niche.created_at.desc())
    )
    return result.scalars().all()


@app.post("/api/niches")
async def create_niche(data: NicheCreate, db: AsyncSession = Depends(get_db)):
    niche = Niche(
        id=str(uuid.uuid4()),
        name=data.name.strip(),
        description=data.description,
    )
    db.add(niche)
    await db.commit()
    await db.refresh(niche)
    return niche


@app.delete("/api/niches/{niche_id}")
async def delete_niche(niche_id: str, db: AsyncSession = Depends(get_db)):
    niche = await db.get(Niche, niche_id)
    if not niche:
        raise HTTPException(404, "Niche not found")
    niche.is_active = False
    await db.commit()
    return {"status": "deleted"}


# ─── Pipeline ─────────────────────────────────────────────────────────────────

class PipelineRequest(BaseModel):
    niche_id: str
    videos_count: Optional[int] = None
    target_duration_sec: Optional[int] = 30
    voice_id: Optional[str] = "male-uk"
    image_source: Optional[str] = "pollinations"  # pollinations | pexels | dalle | mixed


@app.post("/api/pipeline/run")
async def run_pipeline(
    data: PipelineRequest,
    db: AsyncSession = Depends(get_db)
):
    if not settings.has_any_ai:
        raise HTTPException(400,
            "Nenhuma chave AI configurada. Adiciona ao .env:\n"
            "  GROQ_API_KEY=gsk_...  (grátis em console.groq.com)\n"
            "  GEMINI_API_KEY=AIza... (grátis em aistudio.google.com)\n"
            "  OPENAI_API_KEY=sk-...  (pago)"
        )

    niche = await db.get(Niche, data.niche_id)
    if not niche:
        raise HTTPException(404, "Niche not found")

    # Check if already running for this niche
    running = await db.scalar(
        select(func.count(PipelineJob.id))
        .where(PipelineJob.niche_id == data.niche_id)
        .where(PipelineJob.status == JobStatus.RUNNING)
    )
    if running:
        raise HTTPException(409, "Pipeline already running for this niche")

    # Cria o job aqui e passa o id ao orchestrador
    # (antes havia 2 job_ids diferentes — bug corrigido)
    job_id = str(uuid.uuid4())
    job = PipelineJob(
        id=job_id,
        niche_id=niche.id,
        niche_name=niche.name,
        status=JobStatus.RUNNING,
        progress_pct=0,
    )
    db.add(job)
    await db.commit()

    # Corre em background — passa o job_id já criado
    async def run_bg():
        orch = PipelineOrchestrator()
        try:
            await orch.run(niche.id, niche.name, data.videos_count, job_id=job_id, target_duration_sec=data.target_duration_sec, voice_id=data.voice_id, image_source=data.image_source)
        except Exception as e:
            logger.error(f"Background pipeline failed [{job_id}]: {e}")
            # Marcar job como falhado na DB
            try:
                from backend.utils.database import AsyncSessionLocal as _ASL
                async with _ASL() as _db:
                    _j = await _db.get(PipelineJob, job_id)
                    if _j:
                        _j.status = JobStatus.FAILED
                        _j.error_message = str(e)[:500]
                        await _db.commit()
            except Exception:
                pass

    asyncio.create_task(run_bg())

    return {
        "job_id": job_id,
        "niche": niche.name,
        "status": "started",
        "message": f"Generating {data.videos_count or settings.VIDEOS_PER_RUN} videos..."
    }


# ─── Jobs ─────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
async def list_jobs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineJob).order_by(desc(PipelineJob.created_at)).limit(limit)
    )
    return result.scalars().all()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(PipelineJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/jobs/{job_id}/status")
async def job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Lightweight status poll endpoint — called every 2s by frontend."""
    job = await db.get(PipelineJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Get recent logs
    logs_result = await db.execute(
        select(AgentLog)
        .where(AgentLog.job_id == job_id)
        .order_by(desc(AgentLog.id))
        .limit(10)
    )
    logs = list(reversed(logs_result.scalars().all()))

    # Get completed videos
    vids_result = await db.execute(
        select(Video)
        .where(Video.job_id == job_id)
        .where(Video.status == JobStatus.COMPLETED)
    )
    videos = vids_result.scalars().all()

    return {
        "job_id": job_id,
        "status": job.status,
        "current_stage": job.current_stage,
        "progress_pct": job.progress_pct,
        "videos_count": job.videos_count,
        "error": job.error_message,
        "logs": [{"stage": l.stage, "message": l.message, "level": l.level, "time": l.created_at.isoformat()} for l in logs],
        "videos": [_video_dict(v) for v in videos],
    }


@app.get("/api/jobs/{job_id}/logs")
async def job_logs(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentLog).where(AgentLog.job_id == job_id).order_by(AgentLog.id)
    )
    return result.scalars().all()


# ─── Videos ───────────────────────────────────────────────────────────────────

@app.get("/api/videos")
async def list_videos(
    niche_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    q = select(Video).where(Video.status == JobStatus.COMPLETED)
    if niche_id:
        q = q.where(Video.niche_id == niche_id)
    result = await db.execute(q.order_by(desc(Video.created_at)).limit(limit))
    return [_video_dict(v) for v in result.scalars().all()]


@app.get("/api/videos/{video_id}")
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    return _video_dict(video)


@app.get("/api/videos/{video_id}/download")
async def download_video(video_id: str, db: AsyncSession = Depends(get_db)):
    """Download the MP4 file directly."""
    video = await db.get(Video, video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video file not found")
    if not os.path.exists(video.local_path):
        raise HTTPException(410, "Video file was deleted from server")

    filename = f"{video.title[:40] or 'video'}.mp4".replace("/", "_").replace(" ", "_")
    return FileResponse(
        path=video.local_path,
        media_type="video/mp4",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str, db: AsyncSession = Depends(get_db)):
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    # Delete local files
    for path in [video.local_path, video.thumbnail]:
        if path and os.path.exists(path):
            os.remove(path)
    await db.delete(video)
    await db.commit()
    return {"status": "deleted"}


# ─── Stats ────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_videos = await db.scalar(select(func.count(Video.id)).where(Video.status == JobStatus.COMPLETED)) or 0
    total_jobs   = await db.scalar(select(func.count(PipelineJob.id))) or 0
    failed_jobs  = await db.scalar(select(func.count(PipelineJob.id)).where(PipelineJob.status == JobStatus.FAILED)) or 0
    total_niches = await db.scalar(select(func.count(Niche.id)).where(Niche.is_active == True)) or 0
    storage_mb   = await db.scalar(select(func.sum(Video.file_size_mb)).where(Video.status == JobStatus.COMPLETED)) or 0.0

    return {
        "total_videos": total_videos,
        "total_jobs": total_jobs,
        "failed_jobs": failed_jobs,
        "success_rate": round((total_jobs - failed_jobs) / max(total_jobs, 1) * 100, 1),
        "total_niches": total_niches,
        "storage_used_mb": round(storage_mb, 1),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _video_dict(v: Video) -> dict:
    base_url = ""  # Frontend adds base URL
    thumb_url = f"/videos/{Path(v.thumbnail).name}" if v.thumbnail and os.path.exists(v.thumbnail or "") else None
    return {
        "id": v.id,
        "job_id": v.job_id,
        "niche_name": v.niche_name,
        "title": v.title,
        "hook": v.hook,
        "caption": v.caption,
        "hashtags": v.hashtags or [],
        "script": v.script,
        "local_path": v.local_path,
        "thumbnail_url": thumb_url,
        "download_url": f"/api/videos/{v.id}/download",
        "s3_url": v.s3_url,
        "file_size_mb": v.file_size_mb,
        "duration_sec": v.duration_sec,
        "image_source": v.image_source,
        "status": v.status,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }

# ─── Frontend SPA — catch-all (deve ser o ÚLTIMO route) ──────────────────────

@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    """Serve o frontend para todas as rotas não-API."""
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
    
    # Tentar servir ficheiro estático
    file_path = os.path.join(frontend_dir, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Fallback para index.html (SPA routing)
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    raise HTTPException(404, "Frontend not found")
