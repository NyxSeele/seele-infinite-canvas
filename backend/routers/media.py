import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from comfyui import client as comfyui
from core.comfyui_settings import comfyui_http_url
from core.dependencies import get_current_user, get_media_user
from core.logging_setup import studio_print
from db.session import get_db
from models import User
from services.media_access import (
    issue_media_ticket,
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

    upstream_url = f"{comfyui_http_url()}/view"
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
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(
            upstream_url,
            params=params,
            headers=upstream_headers,
        )

    if resp.status_code not in (200, 206):
        studio_print(
            "media",
            f"代理失败 {resp.status_code} filename={safe_name} "
            f"upstream={upstream_url} body={resp.text[:200]}",
        )
        return Response(status_code=resp.status_code, content=resp.text)

    media_type = comfyui.guess_media_type(safe_name, resp.headers.get("content-type", ""))
    out_headers = {}
    for key in _PASS_THROUGH_HEADERS:
        if key in resp.headers:
            out_headers[key] = resp.headers[key]
    if "accept-ranges" not in out_headers and resp.status_code == 200:
        out_headers["Accept-Ranges"] = "bytes"

    studio_print(
        "media",
        f"代理成功 filename={safe_name} status={resp.status_code} "
        f"type={media_type} bytes={len(resp.content)}",
    )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=media_type,
        headers=out_headers,
    )
