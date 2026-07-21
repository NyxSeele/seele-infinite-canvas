"""Backfill tasks.model_id from video_backend for rated tasks."""

from db.session import SessionLocal
from models import Task

BACKEND_TO_MODEL = {
    "wan": "wan-2.6",
    "ltx": "ltx-video",
    "ltx2": "ltx2-video",
    "seedance": "seedance",
}


def main() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(Task)
            .filter(Task.model_id.is_(None))
            .filter(Task.video_backend.isnot(None))
            .all()
        )
        updated = 0
        for task in rows:
            backend = (task.video_backend or "").strip().lower()
            if not backend:
                continue
            task.model_id = BACKEND_TO_MODEL.get(backend, backend)
            updated += 1
        db.commit()
        print(f"backfilled model_id for {updated} tasks")
    finally:
        db.close()


if __name__ == "__main__":
    main()
