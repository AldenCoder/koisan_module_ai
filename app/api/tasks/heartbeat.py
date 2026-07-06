"""Auxiliary scheduled tasks used for demonstration purposes."""

from datetime import datetime, timezone


async def log_scheduler_heartbeat() -> None:
    """Log a heartbeat message to confirm the scheduler is running."""

    now = datetime.now(timezone.utc).isoformat()
    print(f"[Scheduler] Heartbeat logged at {now}.")