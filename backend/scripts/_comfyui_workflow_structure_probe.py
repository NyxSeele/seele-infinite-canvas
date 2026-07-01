"""
ComfyUI Workflow 结构校验探针：向 ComfyUI /prompt 提交 workflow JSON，仅校验节点结构
（不等 GPU 推理）。用于在算力不足时提前发现 HiDream / Wan / Hunyuan 等 workflow 结构性问题。

用法（需本地 ComfyUI 已启动，COMFYUI_URL 可连通）：
  cd backend
  .\\.venv\\Scripts\\python.exe scripts\\_comfyui_workflow_structure_probe.py
  .\\.venv\\Scripts\\python.exe scripts\\_comfyui_workflow_structure_probe.py --model hidream
  .\\.venv\\Scripts\\python.exe scripts\\_comfyui_workflow_structure_probe.py --model wan --comfyui-url http://127.0.0.1:8188
  .\\.venv\\Scripts\\python.exe scripts\\_comfyui_workflow_structure_probe.py --json results.json

前置：在 ComfyUI models/ 下人工放置同名占位权重（几 KB 空文件即可，勿由本脚本创建/覆盖）：
  checkpoints/   v1-5-pruned-emaonly.safetensors
  unet/          flux1-dev.safetensors, hidream_i1_full.safetensors, hunyuan_video_t2v_720p_bf16.safetensors
  clip/          clip_l.safetensors, clip_g.safetensors, llava_llama3_fp8_scaled.safetensors
  vae/           ae.safetensors, hunyuan_video_vae_bf16.safetensors, wan_2.1_vae.safetensors
  text_encoders/ t5xxl_fp16.safetensors, umt5_xxl_fp8_e4m3fn_scaled.safetensors
  Wan 主模型 wan2.6.safetensors 目录以 ComfyUI-WanVideoWrapper 文档为准（常为 diffusion_models/）
  Wan 需安装 ComfyUI-WanVideoWrapper 自定义节点包。

详见 backend/docs/COMFYUI_CUTOVER_RUNBOOK.md 与 model_registry.COMFYUI_LOCAL_PROVIDERS。

注意：hunyuan-video 在 registry 的 comfyui_checkpoint 与 build_hunyuan_video_workflow 默认
HUNYUAN_CKPT 可能不同；本探针使用 builder 运行时实际传入的文件名。
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from comfyui.client import (
    HUNYUAN_CKPT,
    WAN_CKPT,
    build_hunyuan_video_workflow,
    build_wan_video_workflow,
)
from core.comfyui_settings import comfyui_http_url
from model_registry import get_comfyui_provider, resolve_generation_profile
from providers.comfyui import (
    _build_flux_workflow,
    _build_hidream_workflow,
    _build_workflow,
)

PROBE_PROMPT = "AI Studio workflow structure probe"
PROBE_NEGATIVE = "low quality, watermark"
PROBE_SEED = 42
PROBE_IMAGE_SIZE = (512, 512)
PROBE_VIDEO_SIZE = (848, 480)
PROBE_DURATION_SEC = 5

HEALTH_TIMEOUT = 5.0
PROMPT_TIMEOUT = 10.0
QUEUE_TIMEOUT = 5.0

ALL_MODEL_KEYS = ("flux-dev", "sd15", "hidream", "wan", "hunyuan")
BASELINE_KEYS = frozenset({"flux-dev", "sd15"})

HUNYUAN_REGISTRY_NOTE = (
    "registry comfyui_checkpoint 可能为 hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors，"
    f"builder 默认使用 {HUNYUAN_CKPT}"
)


@dataclass
class ProbeTarget:
    key: str
    registry_id: str
    baseline: bool
    category: str  # image | video


PROBE_TARGETS: dict[str, ProbeTarget] = {
    "flux-dev": ProbeTarget("flux-dev", "flux-dev", baseline=True, category="image"),
    "sd15": ProbeTarget("sd15", "stable-diffusion", baseline=True, category="image"),
    "hidream": ProbeTarget("hidream", "hidream", baseline=False, category="image"),
    "wan": ProbeTarget("wan", "wan-2.6", baseline=False, category="video"),
    "hunyuan": ProbeTarget("hunyuan", "hunyuan-video", baseline=False, category="video"),
}


@dataclass
class ProbeResult:
    model: str
    status: str  # PASS | FAIL | HANG | INFRA
    detail: str
    baseline: bool = False
    prompt_id: str | None = None
    node_error_lines: list[str] = field(default_factory=list)
    http_status: int | None = None


def _checkpoint_for(registry_id: str) -> str:
    provider = get_comfyui_provider(registry_id)
    if not provider:
        raise ValueError(f"unknown registry id: {registry_id}")
    return str(provider.get("comfyui_checkpoint") or provider.get("comfyui_file") or "").strip()


def build_workflow_for_target(target: ProbeTarget) -> dict:
    """只读调用现有 builder，固定探针参数。"""
    width_img, height_img = PROBE_IMAGE_SIZE
    width_vid, height_vid = PROBE_VIDEO_SIZE

    if target.key == "flux-dev":
        ckpt = _checkpoint_for(target.registry_id)
        profile = resolve_generation_profile(target.registry_id, ckpt)
        return _build_flux_workflow(
            PROBE_PROMPT, ckpt, width_img, height_img, PROBE_SEED, profile
        )

    if target.key == "sd15":
        ckpt = _checkpoint_for(target.registry_id)
        workflow, _mode = _build_workflow(
            PROBE_PROMPT,
            ckpt,
            width_img,
            height_img,
            seed=PROBE_SEED,
            model_id=target.registry_id,
            negative_prompt=PROBE_NEGATIVE,
        )
        return workflow

    if target.key == "hidream":
        ckpt = _checkpoint_for(target.registry_id)
        profile = resolve_generation_profile(target.registry_id, ckpt)
        return _build_hidream_workflow(
            PROBE_PROMPT, ckpt, width_img, height_img, PROBE_SEED, profile
        )

    if target.key == "wan":
        return build_wan_video_workflow(
            PROBE_PROMPT,
            PROBE_NEGATIVE,
            width=width_vid,
            height=height_vid,
            duration_sec=PROBE_DURATION_SEC,
            seed=PROBE_SEED,
            model_filename=WAN_CKPT,
        )

    if target.key == "hunyuan":
        return build_hunyuan_video_workflow(
            PROBE_PROMPT,
            PROBE_NEGATIVE,
            width=width_vid,
            height=height_vid,
            duration_sec=PROBE_DURATION_SEC,
            seed=PROBE_SEED,
            model_filename=HUNYUAN_CKPT,
        )

    raise ValueError(f"unsupported target: {target.key}")


def flatten_node_errors(model_key: str, node_errors: Any) -> list[str]:
    """整理为 model → node_id → field → error 可读行。"""
    if not node_errors or not isinstance(node_errors, dict):
        return []
    lines: list[str] = []
    for node_id, payload in sorted(node_errors.items(), key=lambda x: str(x[0])):
        if not isinstance(payload, dict):
            lines.append(f"{model_key} → {node_id} → (unknown) → {payload!r}")
            continue
        class_type = payload.get("class_type", "?")
        errors_raw = payload.get("errors")
        if isinstance(errors_raw, list):
            for err in errors_raw:
                if isinstance(err, dict):
                    err_type = err.get("type", "?")
                    err_msg = err.get("details") or err.get("message") or str(err)
                    extra = err.get("extra_info") if isinstance(err.get("extra_info"), dict) else {}
                    field_name = extra.get("input_name", "?")
                    lines.append(
                        f"{model_key} → {node_id} ({class_type}) → {field_name} → "
                        f"{err_type}: {err_msg}"
                    )
                else:
                    lines.append(
                        f"{model_key} → {node_id} ({class_type}) → ? → {err!r}"
                    )
        elif isinstance(errors_raw, dict):
            for field_name, errors in sorted(errors_raw.items()):
                if isinstance(errors, dict):
                    for err_type, err_msg in errors.items():
                        lines.append(
                            f"{model_key} → {node_id} ({class_type}) → {field_name} → "
                            f"{err_type}: {err_msg}"
                        )
                else:
                    lines.append(
                        f"{model_key} → {node_id} ({class_type}) → {field_name} → {errors!r}"
                    )
        if not errors_raw:
            dependent = payload.get("dependent_outputs")
            if dependent:
                lines.append(
                    f"{model_key} → {node_id} ({class_type}) → dependent_outputs → {dependent!r}"
                )
    return lines


def _parse_prompt_response(
    model_key: str,
    *,
    http_status: int,
    body: dict[str, Any],
) -> tuple[str, str, str | None, list[str]]:
    """返回 (status, detail, prompt_id, node_error_lines)。"""
    node_errors = body.get("node_errors") or {}
    error_lines = flatten_node_errors(model_key, node_errors)

    top_error = body.get("error")
    if top_error:
        if isinstance(top_error, dict):
            detail = json.dumps(top_error, ensure_ascii=False)
        else:
            detail = str(top_error)
        if error_lines:
            return "FAIL", error_lines[0], None, error_lines
        return "FAIL", detail, None, error_lines

    if error_lines:
        return "FAIL", error_lines[0], None, error_lines

    prompt_id = body.get("prompt_id")
    if http_status == 200 and prompt_id:
        return "PASS", str(prompt_id), str(prompt_id), []

    if http_status != 200:
        return "FAIL", f"HTTP {http_status}: {json.dumps(body, ensure_ascii=False)[:500]}", None, error_lines

    return "FAIL", f"无 prompt_id: {json.dumps(body, ensure_ascii=False)[:300]}", None, error_lines


def delete_from_queue(client: httpx.Client, comfyui_url: str, prompt_id: str) -> None:
    res = client.post(
        f"{comfyui_url.rstrip('/')}/queue",
        json={"delete": [prompt_id]},
        timeout=QUEUE_TIMEOUT,
    )
    res.raise_for_status()


def submit_workflow(
    client: httpx.Client,
    comfyui_url: str,
    target: ProbeTarget,
    workflow: dict,
) -> ProbeResult:
    base = comfyui_url.rstrip("/")
    client_id = str(uuid.uuid4())
    try:
        res = client.post(
            f"{base}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=PROMPT_TIMEOUT,
        )
    except httpx.TimeoutException:
        return ProbeResult(
            model=target.key,
            status="HANG",
            detail=f"POST /prompt 超时（>{PROMPT_TIMEOUT}s），可能缺失 custom node 或 ComfyUI 未响应",
            baseline=target.baseline,
        )
    except httpx.ConnectError as exc:
        return ProbeResult(
            model=target.key,
            status="INFRA",
            detail=f"连接失败: {exc}",
            baseline=target.baseline,
        )

    try:
        body = res.json()
    except json.JSONDecodeError:
        return ProbeResult(
            model=target.key,
            status="FAIL",
            detail=f"无效 JSON 响应: {res.text[:300]}",
            baseline=target.baseline,
            http_status=res.status_code,
        )

    status, detail, prompt_id, error_lines = _parse_prompt_response(
        target.key,
        http_status=res.status_code,
        body=body,
    )

    if status == "PASS" and prompt_id:
        try:
            delete_from_queue(client, comfyui_url, prompt_id)
        except Exception as exc:
            detail = f"{prompt_id}（queue delete 失败: {exc}）"

    return ProbeResult(
        model=target.key,
        status=status,
        detail=detail,
        baseline=target.baseline,
        prompt_id=prompt_id if status == "PASS" else None,
        node_error_lines=error_lines,
        http_status=res.status_code,
    )


def health_check(client: httpx.Client, comfyui_url: str) -> tuple[bool, str]:
    try:
        res = client.get(f"{comfyui_url.rstrip('/')}/system_stats", timeout=HEALTH_TIMEOUT)
        if res.status_code == 200:
            return True, "ok"
        return False, f"HTTP {res.status_code}"
    except httpx.TimeoutException:
        return False, f"超时（>{HEALTH_TIMEOUT}s）"
    except httpx.ConnectError as exc:
        return False, str(exc)


def run_probe(
    client: httpx.Client,
    comfyui_url: str,
    model_keys: list[str],
) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    for key in model_keys:
        target = PROBE_TARGETS[key]
        print(f"\n[{key}] 构建 workflow …")
        try:
            workflow = build_workflow_for_target(target)
        except Exception as exc:
            results.append(
                ProbeResult(
                    model=key,
                    status="FAIL",
                    detail=f"workflow 构建失败: {exc}",
                    baseline=target.baseline,
                )
            )
            print(f"  FAIL 构建: {exc}")
            continue

        print(f"[{key}] POST /prompt（{len(workflow)} nodes）…")
        result = submit_workflow(client, comfyui_url, target, workflow)
        results.append(result)
        print(f"  {result.status}  {result.detail}")
        for line in result.node_error_lines:
            print(f"    {line}")
        if key == "hunyuan" and result.status == "FAIL":
            print(f"  提示: {HUNYUAN_REGISTRY_NOTE}")

    return results


def print_summary(results: list[ProbeResult]) -> None:
    print("\n" + "=" * 72)
    print(f"{'Model':<12} {'Role':<8} {'Status':<8} Detail")
    print("-" * 72)
    for r in results:
        role = "baseline" if r.baseline else "new"
        detail = r.detail[:48] + ("…" if len(r.detail) > 48 else "")
        print(f"{r.model:<12} {role:<8} {r.status:<8} {detail}")
    print("=" * 72)


def compute_exit_code(results: list[ProbeResult]) -> int:
    if any(r.status == "INFRA" for r in results):
        return 2
    if any(r.baseline and r.status != "PASS" for r in results):
        return 3
    if any(r.status in ("FAIL", "HANG") for r in results):
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ComfyUI workflow 结构校验探针")
    parser.add_argument(
        "--model",
        choices=[*ALL_MODEL_KEYS, "all"],
        default="all",
        help="要校验的模型（默认 all）",
    )
    parser.add_argument(
        "--comfyui-url",
        default="",
        help="覆盖 COMFYUI_URL（默认读环境 / settings）",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        default="",
        help="将结果写入 JSON 文件",
    )
    args = parser.parse_args()

    comfyui_url = (args.comfyui_url or comfyui_http_url()).rstrip("/")
    model_keys = list(ALL_MODEL_KEYS) if args.model == "all" else [args.model]

    print(f"ComfyUI: {comfyui_url}")
    print(f"Models:  {', '.join(model_keys)}")

    with httpx.Client() as client:
        ok, msg = health_check(client, comfyui_url)
        if not ok:
            print(f"\n[INFRA] ComfyUI 不可达: {msg}")
            print("请确认 ComfyUI 已启动且 COMFYUI_URL 正确。")
            return 2
        print("[health] system_stats OK")

        results = run_probe(client, comfyui_url, model_keys)

    print_summary(results)

    if args.json:
        out_path = Path(args.json)
        payload = {
            "comfyui_url": comfyui_url,
            "results": [asdict(r) for r in results],
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {out_path}")

    code = compute_exit_code(results)
    if code == 0:
        print("\n全部通过结构校验（PASS）。")
    elif code == 1:
        print("\n存在结构校验失败（FAIL/HANG），见上表与 node_errors 明细。")
    elif code == 3:
        print("\n基准组未通过：请先检查占位权重文件与 ComfyUI 环境，再怀疑 workflow 代码。")
    return code


if __name__ == "__main__":
    sys.exit(main())
