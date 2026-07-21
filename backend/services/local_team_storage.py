"""Local team file storage on data disk (uploads/team/{team_id}/)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

UPLOAD_ROOT = Path("uploads")
TEAM_MAX_BYTES = 2 * 1024 * 1024 * 1024


def team_upload_dir(team_id: str) -> Path:
    safe = (team_id or "").strip()
    if not safe or "/" in safe or ".." in safe:
        raise HTTPException(status_code=400, detail="无效 team_id")
    path = UPLOAD_ROOT / "team" / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(name: str) -> str:
    base = (name or "file").strip().replace("\\", "/").split("/")[-1]
    if not base or base in {".", ".."}:
        base = "file"
    return base[:200]


def save_team_upload(
    file: UploadFile,
    *,
    team_id: str,
    content_type: str,
) -> dict:
    filename = _safe_filename(file.filename or "file")
    ext = Path(filename).suffix
    stored_name = f"{uuid4().hex}{ext}" if ext else uuid4().hex
    dest_dir = team_upload_dir(team_id)
    dest = dest_dir / stored_name

    try:
        file.file.seek(0, 2)
        size = int(file.file.tell() or 0)
        file.file.seek(0)
    except Exception:
        size = 0

    if size > TEAM_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大允许 {TEAM_MAX_BYTES // (1024 * 1024)} MB",
        )

    written = 0
    with dest.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > TEAM_MAX_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"文件过大，最大允许 {TEAM_MAX_BYTES // (1024 * 1024)} MB",
                )
            out.write(chunk)

    rel_path = f"team/{team_id}/{stored_name}"
    key = f"local/{rel_path}"
    return {
        "key": key,
        "local_rel_path": rel_path,
        "filename": filename,
        "stored_name": stored_name,
        "content_type": content_type or "application/octet-stream",
        "size_bytes": written or size,
    }


def save_local_file_from_path(
    source: Path,
    *,
    team_id: str,
    filename: str,
    content_type: str,
) -> dict:
    dest_dir = team_upload_dir(team_id)
    ext = Path(filename).suffix
    stored_name = f"{uuid4().hex}{ext}" if ext else uuid4().hex
    dest = dest_dir / stored_name
    size = int(source.stat().st_size)
    if size > TEAM_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，最大允许 {TEAM_MAX_BYTES // (1024 * 1024)} MB",
        )
    dest.write_bytes(source.read_bytes())
    rel_path = f"team/{team_id}/{stored_name}"
    return {
        "key": f"local/{rel_path}",
        "local_rel_path": rel_path,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": size,
    }


def resolve_local_path(local_rel_path: str) -> Path:
    rel = (local_rel_path or "").strip().lstrip("/").replace("\\", "/")
    if not rel.startswith("team/"):
        raise HTTPException(status_code=400, detail="非法本地团队路径")
    path = (UPLOAD_ROOT / rel).resolve()
    root = UPLOAD_ROOT.resolve()
    if not str(path).startswith(str(root)) or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return path


def delete_local_file(local_rel_path: str) -> None:
    try:
        path = resolve_local_path(local_rel_path)
        path.unlink(missing_ok=True)
    except HTTPException:
        pass
