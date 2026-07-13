from sqlalchemy import text
from sqlalchemy.engine import Engine


def init_db(engine: Engine) -> None:
    """
    创建 registered_models 表。
    注意：不删除旧 model_settings，避免破坏历史数据。
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS registered_models (
      id            TEXT PRIMARY KEY,
      display_name  TEXT NOT NULL,
      category      TEXT NOT NULL,
      type          TEXT NOT NULL,
      provider      TEXT,
      api_base      TEXT,
      api_key       TEXT,
      model_string  TEXT,
      comfyui_file  TEXT,
      enabled       INTEGER NOT NULL DEFAULT 0,
      created_at    TEXT DEFAULT (datetime('now')),
      updated_at    TEXT DEFAULT (datetime('now'))
    );
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
        _ensure_task_result_columns(conn)


def _ensure_task_result_columns(conn) -> None:
    """为已有 tasks 表补充 result / error / comfyui_prompt_id / node_id 列（SQLite 兼容）。"""
    rows = conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
    if not rows:
        return
    names = {r[1] for r in rows}
    if "result" not in names:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN result TEXT"))
    if "error" not in names:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN error TEXT"))
    if "comfyui_prompt_id" not in names:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN comfyui_prompt_id TEXT"))
    if "node_id" not in names:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN node_id TEXT"))
    if "sound_note" not in names:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN sound_note TEXT"))
    if "video_backend" not in names:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN video_backend TEXT"))
