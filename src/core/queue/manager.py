"""
Job Manager - Handles asynchronous task submission and tracking.
Currently implements a Local Threaded strategy (MVP).
Ready for Celery adaptation.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

# Internal Imports
from src.core.queue.models import Job, JobStatus

logger = logging.getLogger(__name__)


class JobManager:
    _instance = None

    def __init__(self):
        # In-Memory Storage for MVP (Replace with Redis for Production)
        self._jobs: dict[str, Job] = {}

        # Executor for running blocking agent tasks in background
        # max_workers=4 prevents CPU starvation on local machine
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="AgentWorker")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = JobManager()
        return cls._instance

    def submit_job(
        self, user_id: str, task_type: str, payload: dict[str, Any], fn: Callable
    ) -> str:
        """
        Submits a job for execution.

        Args:
            user_id: Owner of the job.
            task_type: Identifier for the task.
            payload: Arguments to pass to the function.
            fn: The actual function to execute (e.g., crew.kickoff).

        Returns:
            job_id: The tracking ID.
        """
        job = Job.create(user_id, task_type, payload)
        self._jobs[job.job_id] = job

        # Submit to background thread
        self._executor.submit(self._execute_wrapper, job.job_id, fn, payload)

        logger.info(f"🚀 Job submitted: {job.job_id} [{task_type}]")
        return job.job_id

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _execute_wrapper(self, job_id: str, fn: Callable, payload: dict[str, Any]):
        """Internal wrapper to handle state transitions and error catching."""
        job = self._jobs.get(job_id)
        if not job:
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        logger.info(f"⚙️ Job Started: {job_id}")

        try:
            # EXECUTE BLOCKING FUNCTION HERE
            result = fn(**payload)

            job.result = result
            job.status = JobStatus.COMPLETED
            logger.info(f"✅ Job Completed: {job_id}")

        except Exception as e:
            job.error = str(e)
            job.status = JobStatus.FAILED
            logger.error(f"❌ Job Failed: {job_id} - {e}", exc_info=True)

        finally:
            job.completed_at = datetime.utcnow()
