"""Cloudflare R2 (S3-compatible) helpers for team file space."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import PurePosixPath
from urllib.parse import quote, unquote
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from core.config import settings

# ASCII-only: non-ASCII names break some public R2 URLs if left unencoded in keys.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class R2NotConfiguredError(RuntimeError):
    """Raised when R2 credentials/bucket are missing."""


def is_r2_configured() -> bool:
    return bool(
        settings.r2_account_id.strip()
        and settings.r2_access_key_id.strip()
        and settings.r2_secret_access_key.strip()
        and settings.r2_bucket_name.strip()
    )


def r2_endpoint_url() -> str:
    account = settings.r2_account_id.strip()
    if not account:
        raise R2NotConfiguredError("R2_ACCOUNT_ID 未配置")
    return f"https://{account}.r2.cloudflarestorage.com"


def r2_public_url_for_key(key: str) -> str:
    base = (settings.r2_public_url or "").strip().rstrip("/")
    if not base:
        raise R2NotConfiguredError("R2_PUBLIC_URL 未配置")
    parts = [p for p in key.lstrip("/").split("/") if p != ""]
    encoded = "/".join(quote(unquote(p), safe=".-_") for p in parts)
    return f"{base}/{encoded}"


def is_r2_public_asset_url(url: str) -> bool:
    base = (settings.r2_public_url or "").strip().rstrip("/")
    if not base or not url:
        return False
    raw = url.strip().split("?")[0]
    return raw.startswith(base + "/") or raw == base


def key_from_r2_public_url(url: str) -> str | None:
    """Extract object key from our R2 public URL, or None if not ours."""
    base = (settings.r2_public_url or "").strip().rstrip("/")
    raw = (url or "").strip().split("?")[0]
    if not base or not raw.startswith(base + "/"):
        return None
    key = unquote(raw[len(base) + 1 :].lstrip("/"))
    return key or None


def ensure_encoded_r2_public_url(url: str | None) -> str | None:
    """Re-encode R2 public URLs so browsers can Range-request non-ASCII keys."""
    if not url:
        return url
    key = key_from_r2_public_url(url)
    if not key:
        return url
    try:
        return r2_public_url_for_key(key)
    except R2NotConfiguredError:
        return url


def _safe_filename(filename: str) -> str:
    name = PurePosixPath((filename or "file").strip()).name or "file"
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("._") or "file"
    # Collapse runs of underscores
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned[:180]


def build_object_key(filename: str, prefix: str = "team") -> str:
    now = datetime.now(timezone.utc)
    safe = _safe_filename(filename)
    root = (prefix or "team").strip().strip("/") or "team"
    return f"{root}/{now:%Y}/{now:%m}/{uuid4().hex}_{safe}"


@lru_cache(maxsize=1)
def _client():
    if not is_r2_configured():
        raise R2NotConfiguredError("R2 未配置（缺少 Account/Key/Bucket）")
    return boto3.client(
        "s3",
        endpoint_url=r2_endpoint_url(),
        aws_access_key_id=settings.r2_access_key_id.strip(),
        aws_secret_access_key=settings.r2_secret_access_key.strip(),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def reset_r2_client_cache() -> None:
    _client.cache_clear()


def generate_presigned_upload_url(
    filename: str,
    content_type: str,
    expires: int = 3600,
    *,
    key: str | None = None,
    prefix: str = "team",
) -> dict:
    """Return {url, key, content_type} for browser PUT upload."""
    object_key = key or build_object_key(filename, prefix=prefix)
    ctype = (content_type or "application/octet-stream").strip()
    try:
        client = _client()
        url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.r2_bucket_name.strip(),
                "Key": object_key,
                "ContentType": ctype,
            },
            ExpiresIn=max(60, int(expires)),
        )
    except R2NotConfiguredError:
        raise
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"生成上传预签名失败: {exc}") from exc
    return {"url": url, "key": object_key, "content_type": ctype}


def upload_fileobj(
    fileobj,
    filename: str,
    content_type: str,
    *,
    prefix: str = "team",
) -> dict:
    """Stream fileobj to R2. Returns {key, content_type, public_url}."""
    object_key = build_object_key(filename, prefix=prefix)
    ctype = (content_type or "application/octet-stream").strip()
    try:
        client = _client()
        client.upload_fileobj(
            fileobj,
            settings.r2_bucket_name.strip(),
            object_key,
            ExtraArgs={"ContentType": ctype},
        )
    except R2NotConfiguredError:
        raise
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"上传到 R2 失败: {exc}") from exc
    return {
        "key": object_key,
        "content_type": ctype,
        "public_url": r2_public_url_for_key(object_key),
    }


def generate_presigned_download_url(key: str, expires: int = 3600) -> str:
    try:
        client = _client()
        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": settings.r2_bucket_name.strip(),
                "Key": key,
            },
            ExpiresIn=max(60, int(expires)),
        )
    except R2NotConfiguredError:
        raise
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"生成下载预签名失败: {exc}") from exc


def list_files(prefix: str = "team/", limit: int = 100) -> list[dict]:
    """List objects from R2. uploader is None unless custom metadata is present."""
    try:
        client = _client()
        resp = client.list_objects_v2(
            Bucket=settings.r2_bucket_name.strip(),
            Prefix=prefix or "team/",
            MaxKeys=max(1, min(int(limit), 1000)),
        )
    except R2NotConfiguredError:
        raise
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"列出 R2 文件失败: {exc}") from exc

    items: list[dict] = []
    for obj in resp.get("Contents") or []:
        key = obj.get("Key") or ""
        meta_uploader = None
        try:
            head = client.head_object(
                Bucket=settings.r2_bucket_name.strip(), Key=key
            )
            meta = head.get("Metadata") or {}
            meta_uploader = meta.get("uploader") or meta.get("uploader-name")
        except (BotoCoreError, ClientError):
            meta_uploader = None
        items.append(
            {
                "key": key,
                "size": int(obj.get("Size") or 0),
                "uploaded_at": obj.get("LastModified"),
                "uploader": meta_uploader,
            }
        )
    return items


def delete_file(key: str) -> None:
    try:
        client = _client()
        client.delete_object(
            Bucket=settings.r2_bucket_name.strip(),
            Key=key,
        )
    except R2NotConfiguredError:
        raise
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"删除 R2 文件失败: {exc}") from exc
