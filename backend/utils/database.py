"""
Database models — simplified for video generation + download focus.
Uses SQLite by default (zero config), Postgres in production.
"""
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, Text, Enum, JSON, event
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.utils.config import settings

# SQLite needs check_same_thread=False
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args,
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ─── Enums ───────────────────────────────────────────────────────────────────

class JobStatus(str, PyEnum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"

class AgentStage(str, PyEnum):
    TREND     = "trend_analysis"
    STRATEGY  = "content_strategy"
    SCRIPT    = "script_generation"
    VISUAL    = "visual_generation"
    VOICEOVER = "voiceover"
    ASSEMBLY  = "video_assembly"
    SEO       = "seo_captions"


# ─── Models ──────────────────────────────────────────────────────────────────

class Niche(Base):
    __tablename__ = "niches"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String, nullable=False)
    description = Column(Text, default="")
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    niche_id      = Column(String, nullable=False)
    niche_name    = Column(String, nullable=False)
    status        = Column(Enum(JobStatus), default=JobStatus.PENDING)
    current_stage = Column(Enum(AgentStage), nullable=True)
    progress_pct  = Column(Integer, default=0)        # 0–100
    retry_count   = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    videos_count  = Column(Integer, default=0)
    created_at    = Column(DateTime, default=datetime.utcnow)
    completed_at  = Column(DateTime, nullable=True)


class Video(Base):
    __tablename__ = "videos"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id       = Column(String, nullable=False)
    niche_id     = Column(String, nullable=False)
    niche_name   = Column(String, nullable=False)

    # Content
    title        = Column(String, default="")
    script       = Column(Text, default="")
    hook         = Column(Text, default="")
    caption      = Column(Text, default="")
    hashtags     = Column(JSON, default=list)

    # Files
    local_path   = Column(String, nullable=True)   # Local MP4 path
    s3_url       = Column(String, nullable=True)   # Optional cloud URL
    thumbnail    = Column(String, nullable=True)   # Thumbnail path
    file_size_mb = Column(Float, default=0.0)
    duration_sec = Column(Float, default=0.0)

    # Metadata
    image_source = Column(String, default="pexels")  # pexels | dalle | stability
    status       = Column(Enum(JobStatus), default=JobStatus.PENDING)
    created_at   = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error        = Column(Text, nullable=True)


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    job_id     = Column(String, nullable=False)
    stage      = Column(String, nullable=False)
    level      = Column(String, default="INFO")
    message    = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Init ─────────────────────────────────────────────────────────────────────

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
