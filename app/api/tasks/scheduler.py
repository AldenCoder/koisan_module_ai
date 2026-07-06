from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Mapping

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger

from app.tasks.heartbeat import log_scheduler_heartbeat
from app.tasks.order_expiry import deactivate_expired_orders

JobCallable = Callable[..., Awaitable[None]]


@dataclass(frozen=True)
class SchedulerJob:
    """Declarative description of a scheduled task."""

    id: str
    func: JobCallable
    trigger: BaseTrigger
    kwargs: Mapping[str, object] = field(default_factory=dict)
    options: Mapping[str, object] = field(default_factory=dict)


DEFAULT_JOBS: tuple[SchedulerJob, ...] = (
    SchedulerJob(
        id="deactivate_expired_orders",
        func=deactivate_expired_orders,
        trigger=CronTrigger(hour=0, minute=0),
        options={"replace_existing": True},
    ),
    SchedulerJob(
        id="log_scheduler_heartbeat",
        func=log_scheduler_heartbeat,
        trigger=CronTrigger(minute="*/5"),
        options={"replace_existing": True},
    ),
)


scheduler = AsyncIOScheduler()


def _configure_jobs(jobs: Iterable[SchedulerJob]) -> None:
    for job in jobs:
        scheduler.add_job(
            job.func,
            job.trigger,
            id=job.id,
            kwargs=dict(job.kwargs),
            **({"replace_existing": True} | dict(job.options)),
        )


def start_scheduler(jobs: Iterable[SchedulerJob] | None = None) -> None:
    """Start the APScheduler instance with the provided jobs."""

    job_definitions = tuple(jobs) if jobs is not None else DEFAULT_JOBS
    _configure_jobs(job_definitions)
    scheduler.start()
    print(f"[Scheduler] Đã khởi động {len(job_definitions)} tác vụ.")


def stop_scheduler(wait: bool = True) -> None:
    scheduler.shutdown(wait=wait)
    print("[Scheduler] Đã dừng.")