"""媒体访问鉴权：JWT 用户 + 短效 mt 令牌（供 video/img 标签）+ 资源归属校验。"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from models import Task, User
from services.redis_client import get_redis

_OUTPUT_GRANT_TTL = 7200
_memory_output_grants: dict[str, float] = {}

_FILENAME_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
_UPLOAD_PATH = re.compile(
    r"^(?:images|videos|audio)/[A-Za-z0-9._-]+$|^luts/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.cube$"
)


def _signing_key() -> bytes:
    return hashlib.sha256(
        f"{settings.jwt_secret}:media-access".encode("utf-8")
    ).digest()


def _b64_encode(raw: bytes) -> str:
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    from base64 import urlsafe_b64decode

    return urlsafe_b64decode(text + pad)


def issue_media_ticket(user_id: int, ttl: int | None = None) -> dict[str, Any]:
    """签发用户级媒体访问票据（前端附加到 /api/view、/api/uploads URL）。"""
    lifetime = int(ttl or settings.media_token_ttl_seconds)
    exp = int(time.time()) + max(60, lifetime)
    payload = {"uid": int(user_id), "exp": exp}
    body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_signing_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    token = f"{body}.{sig}"
    return {"media_ticket": token, "expires_at": exp}


def verify_media_ticket(token: str | None) -> int | None:
    if not token or "." not in token:
        return None
    body, sig = token.split(".", 1)
    expected = hmac.new(_signing_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(_b64_decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    uid = payload.get("uid")
    if uid is None:
        return None
    return int(uid)


def sanitize_filename(filename: str) -> str:
    name = (filename or "").strip().replace("\\", "/").split("/")[-1]
    if not name or not _FILENAME_SAFE.match(name):
        raise HTTPException(status_code=400, detail="非法文件名")
    return name


def sanitize_upload_rel_path(rel: str) -> str:
    path = (rel or "").strip().lstrip("/").replace("\\", "/")
    if not _UPLOAD_PATH.match(path):
        raise HTTPException(status_code=400, detail="非法上传路径")
    return path


def _teammate_user_ids(db: Session, user_id: int) -> set[int]:
    from models.team import TeamMember

    my_team_ids = [
        r[0]
        for r in db.query(TeamMember.team_id)
        .filter(TeamMember.user_id == user_id)
        .all()
    ]
    if not my_team_ids:
        return set()
    rows = (
        db.query(TeamMember.user_id)
        .filter(TeamMember.team_id.in_(my_team_ids))
        .filter(TeamMember.user_id != user_id)
        .distinct()
        .all()
    )
    return {int(r[0]) for r in rows}


def _output_grant_key(user_id: int, safe_name: str) -> str:
    return f"media:grant:{user_id}:{safe_name}"


def _extract_output_filename(url: str) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    if "filename=" in raw:
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(raw).query)
        names = query.get("filename") or []
        if names and names[0]:
            return sanitize_filename(names[0])
    if raw.startswith("/api/view"):
        return None
    if "/" not in raw and "\\" not in raw:
        return sanitize_filename(raw)
    return sanitize_filename(raw.rsplit("/", 1)[-1])


def grant_output_access(user_id: int, url: str | None, *, ttl: int = _OUTPUT_GRANT_TTL) -> None:
    """登记用户可访问的 Comfy 输出文件名（生成过程中 result 可能尚未入库）。"""
    if not user_id:
        return
    try:
        safe_name = _extract_output_filename(url or "")
    except HTTPException:
        return
    if not safe_name:
        return
    key = _output_grant_key(user_id, safe_name)
    client = get_redis()
    if client is not None:
        try:
            client.setex(key, max(60, ttl), "1")
            return
        except Exception:
            pass
    import time

    _memory_output_grants[key] = time.time() + max(60, ttl)


def _has_output_grant(user_id: int, safe_name: str) -> bool:
    key = _output_grant_key(user_id, safe_name)
    client = get_redis()
    if client is not None:
        try:
            return bool(client.get(key))
        except Exception:
            pass
    import time

    expires = _memory_output_grants.get(key)
    if not expires:
        return False
    if expires < time.time():
        _memory_output_grants.pop(key, None)
        return False
    return True


def _active_task_matches_output(
    db: Session, owner_id: int, needle: str, safe_name: str
) -> bool:
    rows = (
        db.query(Task.result)
        .filter(Task.user_id == owner_id)
        .filter(Task.task_type.in_(("image", "video")))
        .filter(Task.status.in_(("pending", "queued", "running")))
        .all()
    )
    for (result,) in rows:
        if not result:
            continue
        if needle in result or safe_name in result:
            return True
    return False


def _task_contains_output(db: Session, owner_id: int, needle: str, safe_name: str) -> bool:
    if (
        db.query(Task.id)
        .filter(Task.user_id == owner_id)
        .filter(Task.result.isnot(None))
        .filter(Task.result.contains(needle))
        .limit(1)
        .first()
        is not None
    ):
        return True
    return (
        db.query(Task.id)
        .filter(Task.user_id == owner_id)
        .filter(Task.result.isnot(None))
        .filter(Task.result.contains(safe_name))
        .limit(1)
        .first()
        is not None
    )


def user_can_access_comfy_output(
    db: Session,
    user: User,
    filename: str,
    *,
    subfolder: str = "",
) -> bool:
    if user.role == "admin":
        return True
    safe_name = sanitize_filename(filename)
    needle = safe_name
    if subfolder:
        needle = f"{subfolder}/{safe_name}"
    if _task_contains_output(db, user.id, needle, safe_name):
        return True
    if _has_output_grant(user.id, safe_name):
        return True
    if _active_task_matches_output(db, user.id, needle, safe_name):
        return True
    for teammate_id in _teammate_user_ids(db, user.id):
        if _task_contains_output(db, teammate_id, needle, safe_name):
            return True
        if _has_output_grant(teammate_id, safe_name):
            return True
        if _active_task_matches_output(db, teammate_id, needle, safe_name):
            return True
    return False


def user_can_access_upload(db: Session, user: User, rel_path: str) -> bool:
    if user.role == "admin":
        return True
    filename = rel_path.split("/")[-1]
    if (
        db.query(Task.id)
        .filter(Task.user_id == user.id)
        .filter(Task.result.isnot(None))
        .filter(Task.result.contains(filename))
        .first()
    ):
        return True
    from models.user_upload import UserUpload

    owned = (
        db.query(UserUpload.id)
        .filter(UserUpload.user_id == user.id, UserUpload.path == rel_path)
        .first()
    )
    if owned:
        return True
    upload_owner = (
        db.query(UserUpload.user_id)
        .filter(UserUpload.path == rel_path)
        .first()
    )
    if upload_owner and int(upload_owner[0]) in _teammate_user_ids(db, user.id):
        return True
    # 用户资料头像（users.avatar_url）对队友可见
    avatar_suffix = f"/api/uploads/{rel_path}"
    profile_owners = (
        db.query(User.id)
        .filter(User.avatar_url == avatar_suffix)
        .all()
    )
    teammates = _teammate_user_ids(db, user.id)
    for (owner_id,) in profile_owners:
        if int(owner_id) == user.id or int(owner_id) in teammates:
            return True
    return False


def resolve_media_user(
    db: Session,
    *,
    bearer_user: User | None,
    media_ticket: str | None,
) -> User:
    if bearer_user is not None:
        return bearer_user
    uid = verify_media_ticket(media_ticket)
    if uid is None:
        raise HTTPException(status_code=401, detail="未登录或媒体访问票据无效")
    user = db.get(User, uid)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user


def append_media_ticket(url: str, ticket: str) -> str:
    if not url or not ticket:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}mt={quote(ticket, safe='')}"


def build_signed_view_url(
    filename: str,
    *,
    user_id: int,
    media_type: str = "output",
    subfolder: str = "",
) -> str:
    ticket = issue_media_ticket(user_id)["media_ticket"]
    params: dict[str, str] = {
        "filename": sanitize_filename(filename),
        "type": media_type or "output",
        "mt": ticket,
    }
    if subfolder:
        params["subfolder"] = subfolder
    return f"/api/view?{urlencode(params)}"


UPLOAD_ROOT = Path("uploads")


def normalize_media_reference_url(url: str) -> str:
    """
    将 http(s)://{本机}/api/view|uploads/... 剥回 path?query；去掉 mt。
    真正外部 URL 原样返回（仍以 http 开头）。
    """
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    raw = (url or "").strip()
    if not raw:
        return raw
    if raw.startswith("data:") or raw.startswith("blob:"):
        return raw

    parsed = None
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        path = parsed.path or ""
        if path.startswith("/api/view") or path.startswith("/api/uploads/") or path.startswith(
            "/uploads/"
        ):
            # 本机 API 媒体路径 → 相对
            q = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "mt"]
            return urlunparse(("", "", path, "", urlencode(q), ""))
        return raw  # 外部 URL

    # 相对路径：去掉 mt
    if "?" in raw:
        path, _, query = raw.partition("?")
        q = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k != "mt"]
        return f"{path}?{urlencode(q)}" if q else path
    return raw


def ref_url_to_rel_path(image_url: str) -> str:
    """将 /api/uploads/... 或 /uploads/... 转为 images/xxx 相对路径。"""
    raw = normalize_media_reference_url((image_url or "").strip())
    if not raw:
        raise HTTPException(status_code=400, detail="参考图地址为空")
    if "?" in raw and "/api/view" not in raw.split("?", 1)[0]:
        raw = raw.split("?", 1)[0]
    if raw.startswith("http://") or raw.startswith("https://"):
        path = urlparse(raw).path or ""
        raw = path
    for prefix in ("/api/uploads/", "/uploads/", "api/uploads/", "uploads/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    if raw.startswith("/"):
        raw = raw.lstrip("/")
    return sanitize_upload_rel_path(raw)


def resolve_upload_file_path(rel: str) -> Path:
    rel = sanitize_upload_rel_path(rel)
    root = UPLOAD_ROOT.resolve()
    full = (UPLOAD_ROOT / rel).resolve()
    if not str(full).startswith(str(root)):
        raise HTTPException(status_code=400, detail="非法上传路径")
    return full


def _resolve_comfy_output_path(filename: str, subfolder: str = "") -> Path | None:
    """解析 Comfy 输出文件磁盘路径（与 export_service 逻辑一致）。"""
    from pathlib import Path as _Path

    safe_name = sanitize_filename(filename)
    sub = (subfolder or "").strip().replace("\\", "/").strip("/")
    backend_dir = _Path(__file__).resolve().parent.parent
    search_roots = [
        backend_dir / "output",
        backend_dir.parent / "output",
        backend_dir.parent.parent / "ComfyUI" / "output",
        UPLOAD_ROOT,
    ]
    for root in search_roots:
        if sub:
            candidate = root / sub / safe_name
            if candidate.is_file():
                return candidate.resolve()
        candidate = root / safe_name
        if candidate.is_file():
            return candidate.resolve()
    return None


def resolve_video_source_for_enhance(db: Session, user: User, video_url: str) -> Path | None:
    """
    解析画质增强可用的本地视频路径。
    - /api/view?filename=...：校验 Comfy 输出访问权后返回磁盘路径
    - /api/uploads/videos/...：沿用上传校验
    - 外部 http(s)://：返回 None，由 upload_video_from_url 下载
    """
    raw = normalize_media_reference_url((video_url or "").strip())
    if not raw:
        raise HTTPException(status_code=400, detail="视频地址不能为空")
    if raw.startswith("http://") or raw.startswith("https://"):
        return None
    if "filename=" in raw or raw.startswith("/api/view"):
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(raw).query)
        names = query.get("filename") or []
        if not names or not names[0]:
            raise HTTPException(status_code=400, detail="视频源无效或无权访问")
        filename = names[0]
        subfolders = query.get("subfolder") or [""]
        subfolder = (subfolders[0] or "").strip()
        if not user_can_access_comfy_output(db, user, filename, subfolder=subfolder):
            raise HTTPException(status_code=403, detail="视频源无效或无权访问")
        path = _resolve_comfy_output_path(filename, subfolder)
        if not path or not path.is_file():
            raise HTTPException(status_code=404, detail="视频文件不存在，请重新生成后再试")
        return path
    try:
        return assert_user_can_read_upload_url(db, user, raw)
    except HTTPException as exc:
        if exc.status_code == 400 and exc.detail == "非法上传路径":
            raise HTTPException(status_code=400, detail="视频源无效或无权访问") from exc
        raise


def resolve_image_reference_path(db: Session, user: User, image_url: str) -> Path:
    """
    解析图生视频 / 图生图可用的本地参考图路径。
    - /api/view?filename=...：校验 Comfy 输出访问权后返回磁盘路径
    - /api/uploads/images/...：沿用上传校验
    """
    raw = normalize_media_reference_url((image_url or "").strip())
    if not raw:
        raise HTTPException(status_code=400, detail="参考图地址不能为空")
    if raw.startswith("http://") or raw.startswith("https://"):
        raise HTTPException(status_code=400, detail="参考图无效或无权访问")
    if "filename=" in raw or raw.startswith("/api/view"):
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(raw).query)
        names = query.get("filename") or []
        if not names or not names[0]:
            raise HTTPException(status_code=400, detail="参考图无效或无权访问")
        filename = names[0]
        subfolders = query.get("subfolder") or [""]
        subfolder = (subfolders[0] or "").strip()
        if not user_can_access_comfy_output(db, user, filename, subfolder=subfolder):
            raise HTTPException(status_code=403, detail="参考图无效或无权访问")
        path = _resolve_comfy_output_path(filename, subfolder)
        if not path or not path.is_file():
            raise HTTPException(status_code=404, detail="参考图文件不存在，请重新生成后再试")
        return path
    try:
        return assert_user_can_read_upload_url(db, user, raw)
    except HTTPException as exc:
        if exc.status_code == 400 and exc.detail == "非法上传路径":
            raise HTTPException(status_code=400, detail="参考图无效或无权访问") from exc
        raise


def assert_user_can_read_upload_url(db: Session, user: User, image_url: str) -> Path:
    """校验用户可读该上传文件，返回磁盘绝对路径（仅限 uploads/images|videos）。"""
    rel = ref_url_to_rel_path(image_url)
    if not user_can_access_upload(db, user, rel):
        raise HTTPException(status_code=403, detail="无权访问该参考图")
    path = resolve_upload_file_path(rel)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="参考图文件不存在")
    return path
