"""
Sistema de Fila (Queue) para processamento de múltiplos vídeos
"""

import logging
import threading
import queue
import uuid
import json
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from config.settings import QUEUE_DIR, MAX_QUEUE_SIZE, MAX_CONCURRENT_JOBS

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoJob:
    """Representa um job de geração de vídeo na fila."""

    def __init__(self, config: dict):
        self.job_id = str(uuid.uuid4())[:8]
        self.config = config
        self.status = JobStatus.PENDING
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.result = None
        self.progress_step = 0
        self.progress_total = 6
        self.progress_message = "Na fila..."

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "config": self.config,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress_step": self.progress_step,
            "progress_total": self.progress_total,
            "progress_message": self.progress_message,
            "result": self.result,
        }


class VideoQueue:
    """Sistema de fila para processamento de vídeos."""

    def __init__(self, pipeline=None):
        self.pipeline = pipeline
        self._queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self._jobs: Dict[str, VideoJob] = {}
        self._lock = threading.Lock()
        self._workers = []
        self._running = False
        self._on_job_complete: Optional[Callable] = None

        # Carrega jobs persistidos
        self._load_persisted_jobs()

    def set_pipeline(self, pipeline):
        """Define o pipeline a usar."""
        self.pipeline = pipeline

    def set_on_complete_callback(self, callback: Callable):
        """Define callback chamado quando um job completa."""
        self._on_job_complete = callback

    def start(self, num_workers: int = MAX_CONCURRENT_JOBS):
        """Inicia os workers da fila."""
        if self._running:
            return

        self._running = True
        logger.info(f"Iniciando fila com {num_workers} workers")

        for i in range(num_workers):
            t = threading.Thread(
                target=self._worker,
                name=f"VideoWorker-{i+1}",
                daemon=True
            )
            t.start()
            self._workers.append(t)

    def stop(self):
        """Para os workers."""
        self._running = False

    def add_job(self, config: dict) -> VideoJob:
        """
        Adiciona um job à fila.

        Args:
            config: Configuração do vídeo a gerar

        Returns:
            VideoJob criado
        """
        job = VideoJob(config)
        job.config["job_id"] = job.job_id

        with self._lock:
            self._jobs[job.job_id] = job

        try:
            self._queue.put(job, timeout=5)
            self._persist_job(job)
            logger.info(f"Job {job.job_id} adicionado à fila. Total na fila: {self._queue.qsize()}")
        except queue.Full:
            job.status = JobStatus.FAILED
            job.result = {"error": "Fila cheia! Tente mais tarde."}
            logger.error(f"Fila cheia! Job {job.job_id} rejeitado.")

        return job

    def get_job(self, job_id: str) -> Optional[VideoJob]:
        """Obtém um job pelo ID."""
        return self._jobs.get(job_id)

    def get_all_jobs(self) -> list:
        """Retorna todos os jobs."""
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def get_queue_size(self) -> int:
        """Retorna tamanho atual da fila."""
        return self._queue.qsize()

    def cancel_job(self, job_id: str) -> bool:
        """Tenta cancelar um job pendente."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status == JobStatus.PENDING:
                job.status = JobStatus.CANCELLED
                return True
        return False

    def _worker(self):
        """Worker que processa jobs da fila."""
        name = threading.current_thread().name
        logger.info(f"Worker {name} iniciado")

        while self._running:
            try:
                job = self._queue.get(timeout=2)

                # Verifica se foi cancelado enquanto esperava
                if job.status == JobStatus.CANCELLED:
                    self._queue.task_done()
                    continue

                # Processa o job
                self._process_job(job)
                self._queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker {name} erro: {e}")

    def _process_job(self, job: VideoJob):
        """Processa um job individual."""
        logger.info(f"Processando job {job.job_id}")

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now()
        self._persist_job(job)

        def progress_callback(step, total, message, jid):
            job.progress_step = step
            job.progress_total = total
            job.progress_message = message
            self._persist_job(job)

        try:
            config = {k: v for k, v in job.config.items() if k != "job_id"}
            result = self.pipeline.generate_video(
                **config,
                job_id=job.job_id,
                progress_callback=progress_callback
            )

            job.result = result
            job.status = JobStatus.COMPLETED if result["success"] else JobStatus.FAILED
            job.progress_step = job.progress_total
            job.progress_message = "✅ Concluído!" if result["success"] else f"❌ Erro: {result['error']}"

        except Exception as e:
            job.status = JobStatus.FAILED
            job.result = {"success": False, "error": str(e)}
            job.progress_message = f"❌ Erro: {str(e)[:100]}"
            logger.error(f"Job {job.job_id} falhou: {e}", exc_info=True)
        finally:
            job.completed_at = datetime.now()
            self._persist_job(job)

            if self._on_job_complete:
                try:
                    self._on_job_complete(job)
                except Exception:
                    pass

    def _persist_job(self, job: VideoJob):
        """Persiste estado do job em disco."""
        try:
            path = QUEUE_DIR / f"{job.job_id}.json"
            with open(path, "w") as f:
                json.dump(job.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

    def _load_persisted_jobs(self):
        """Carrega jobs persistidos do disco."""
        try:
            for f in QUEUE_DIR.glob("*.json"):
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                    # Apenas carrega para histórico (não re-executa)
                    if data.get("status") in ["completed", "failed", "cancelled"]:
                        job = VideoJob(data.get("config", {}))
                        job.job_id = data["job_id"]
                        job.status = JobStatus(data["status"])
                        job.result = data.get("result")
                        self._jobs[job.job_id] = job
                except Exception:
                    pass
        except Exception:
            pass
