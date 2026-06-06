from datetime import datetime

from app.storage.models import PipelineRun


def start_run(session, run_type: str, snapshot_date=None) -> PipelineRun:
    run = PipelineRun(
        run_type=run_type,
        status="running",
        snapshot_date=snapshot_date,
    )
    session.add(run)
    session.commit()
    return run


def finish_run(
    session,
    run_id: int,
    status: str,
    message: str | None = None,
    raw_count: int | None = None,
    curated_count: int | None = None,
    top_count: int | None = None,
):
    run = session.query(PipelineRun).filter(PipelineRun.id == run_id).one()
    run.status = status
    run.finished_at = datetime.utcnow()
    run.message = message
    run.raw_count = raw_count
    run.curated_count = curated_count
    run.top_count = top_count
    session.commit()