import logging
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from comfyui import client as comfyui
from core.comfyui_settings import resolve_comfyui_node_url
from core.config import settings
from core.dependencies import get_current_user, get_media_user, security
from core.logging_setup import studio_print
from db.session import get_db
from models import User
from services.media_access import (
    issue_media_ticket,
    resolve_media_user,
    sanitize_filename,
    sanitize_upload_rel_path,
    user_can_access_comfy_output,
    user_can_access_upload,
)

router = APIRouter(tags=["media"])
logger = logging.getLogger(__name__)

_PASS_THROUGH_HEADERS = (
    "content-range",
    "accept-ranges",
    "content-length",
    "content-type",
    "etag",
    "last-modified",
)

_UPLOAD_ROOT = Path("uploads")


@router.get("/api/media/ticket")
async def issue_user_media_ticket(user: User = Depends(get_current_user)):
    """签发短效媒体票据，供 video/img 标签附加到 URL（?mt=）。"""
    return issue_media_ticket(user.id)


@router.get("/api/media/auth-check")
async def media_auth_check(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_db),
    mt: str | None = Query(None, alias="mt"),
):
    """
    Nginx auth_request 子请求：只校验 Bearer/?mt= 与资源归属，不读文件体。
    视频文件由 Nginx 静态直出（见 deploy/nginx-*.conf）。

    注意：auth_request 子请求的 $args 常为空，mt 需从 X-Original-URI 回读。
    """
    original = request.headers.get("x-original-uri") or ""
    path = urlparse(original).path if original else ""
    if not (mt or "").strip() and original:
        qs = parse_qs(urlparse(original).query)
        vals = qs.get("mt") or []
        mt = vals[0] if vals else None

    bearer_user = None
    if credentials and credentials.scheme.lower() == "bearer":
        bearer_user = get_current_user(credentials, db)
    user = resolve_media_user(db, bearer_user=bearer_user, media_ticket=mt)

    prefix = "/api/uploads/"
    if not path.startswith(prefix):
        raise HTTPException(status_code=400, detail="非法媒体路径")
    safe_rel = sanitize_upload_rel_path(path[len(prefix) :])
    if not user_can_access_upload(db, user, safe_rel):
        raise HTTPException(status_code=403, detail="无权访问该上传文件")
    return Response(status_code=200)


@router.get("/api/storage/info")
async def storage_info(user: User = Depends(get_current_user)):
    try:
        return await comfyui.get_storage_info()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"无法获取 ComfyUI 存储信息: {e.response.text}",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取存储信息失败: {e}") from e


@router.get("/api/uploads/{rel_path:path}")
async def serve_upload(
    rel_path: str,
    user: User = Depends(get_media_user),
    db: Session = Depends(get_db),
):
    """回退路径：直连后端时仍可用；生产环境视频由 Nginx 静态直出。"""
    safe_rel = sanitize_upload_rel_path(rel_path)
    if not user_can_access_upload(db, user, safe_rel):
        raise HTTPException(status_code=403, detail="无权访问该上传文件")
    file_path = (_UPLOAD_ROOT / safe_rel).resolve()
    root = _UPLOAD_ROOT.resolve()
    if not str(file_path).startswith(str(root)) or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path)


@router.get("/api/view")
async def proxy_view(
    request: Request,
    filename: str = Query(...),
    type: str = Query("output"),
    subfolder: str = Query(""),
    node: str | None = Query(None),
    user: User = Depends(get_media_user),
    db: Session = Depends(get_db),
):
    safe_name = sanitize_filename(filename)
    safe_subfolder = (subfolder or "").strip().replace("\\", "/").strip("/")
    if safe_subfolder and not all(
        part and part not in (".", "..") for part in safe_subfolder.split("/")
    ):
        raise HTTPException(status_code=400, detail="非法 subfolder")

    if not user_can_access_comfy_output(
        db, user, safe_name, subfolder=safe_subfolder
    ):
        raise HTTPException(status_code=403, detail="无权访问该媒体文件")

    params = {"filename": safe_name, "type": type or "output"}
    if safe_subfolder:
        params["subfolder"] = safe_subfolder

    upstream_url = f"{resolve_comfyui_node_url(node)}/view"
    upstream_headers = {}
    range_header = request.headers.get("range")
    if range_header:
        upstream_headers["Range"] = range_header

    logger.info(
        "proxy_view user=%s filename=%s type=%s subfolder=%s range=%s",
        user.id,
        safe_name,
        type,
        safe_subfolder,
        bool(range_header),
    )

    # Stream body to avoid buffering entire video (Cloudflare 100s / memory).
    timeout = httpx.Timeout(float(settings.llm_http_timeout), connect=30.0)
    client = httpx.AsyncClient(timeout=timeout)
    try:
        req = client.build_request(
            "GET",
            upstream_url,
            params=params,
            headers=upstream_headers,
        )
        resp = await client.send(req, stream=True)
    except Exception:
        await client.aclose()
        raise

    if resp.status_code not in (200, 206):
        body = await resp.aread()
        await resp.aclose()
        await client.aclose()
        text = body.decode("utf-8", errors="replace")
        studio_print(
            "media",
            f"代理失败 {resp.status_code} filename={safe_name} "
            f"upstream={upstream_url} body={text[:200]}",
        )
        return Response(status_code=resp.status_code, content=body)

    media_type = comfyui.guess_media_type(
        safe_name, resp.headers.get("content-type", "")
    )
    out_headers = {}
    for key in _PASS_THROUGH_HEADERS:
        if key in resp.headers:
            out_headers[key] = resp.headers[key]
    if "accept-ranges" not in {k.lower() for k in out_headers} and resp.status_code == 200:
        out_headers["Accept-Ranges"] = "bytes"

    content_length = resp.headers.get("content-length", "?")
    studio_print(
        "media",
        f"代理成功(stream) filename={safe_name} status={resp.status_code} "
        f"type={media_type} content_length={content_length}",
    )

    async def body_iter():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        body_iter(),
        status_code=resp.status_code,
        media_type=media_type,
        headers=out_headers,
    )
