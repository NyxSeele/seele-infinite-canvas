"""registered_models 辅助：解析实际 API 调用名。"""

import re

OFFICIAL_MODEL_NAME_RE = re.compile(r"[.:_]")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")
MODEL_ID_INVALID_MSG = (
    "模型ID仅作为内部标识，请填写字母数字和连字符；官方模型名请填写在模型调用名字段。"
)


def slugify_model_id(raw: str) -> str:
    """将官方模型名转为内部 model_id（仅字母数字连字符）。"""
    s = re.sub(r"[.:_]+", "-", (raw or "").strip())
    s = re.sub(r"[^A-Za-z0-9-]", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def normalize_openai_compatible_base(api_base: str) -> str:
    """
    百炼 / MaaS 控制台常给出 DashScope 原生 /api/v1；
    OpenAI SDK 需使用 compatible-mode/v1。
    """
    url = (api_base or "").strip().rstrip("/")
    if not url:
        return url
    lower = url.lower()
    if "dashscope.aliyuncs.com" not in lower and "maas.aliyuncs.com" not in lower:
        return url
    if url.endswith("/api/v1"):
        return f"{url[:-len('/api/v1')]}/compatible-mode/v1"
    if url.endswith("/api"):
        return f"{url}/compatible-mode/v1"
    if "compatible-mode" not in lower and not lower.endswith("/v1"):
        return f"{url}/compatible-mode/v1"
    return url


def resolve_api_model_name(
    model_id: str,
    model_string: str | None = None,
    *,
    display_name: str | None = None,
) -> str:
    """实际传给上游 API 的 model 参数。"""
    mid = (model_id or "").strip()
    explicit = (model_string or "").strip()
    if explicit and explicit != mid:
        return explicit
    dn = (display_name or "").strip()
    if dn and dn != mid and OFFICIAL_MODEL_NAME_RE.search(dn):
        return dn
    return explicit or mid
