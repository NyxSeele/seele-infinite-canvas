#!/usr/bin/env python3
"""G47: GPUPool 单节点注册 / 忙闲 / 短长队列分流探针（无需真实 GPU）。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from routers.tasks import estimate_duration, estimate_queue_bucket
from services.gpu_pool import (
    GPUNode,
    GPUPool,
    SHORT_TASK_THRESHOLD_SEC,
    queue_bucket,
    reset_gpu_pool_for_tests,
)

OUT = Path("/root/autodl-tmp/logs/g47_gpu_pool_probe.json")


def main() -> int:
    issues: list[str] = []
    results: dict = {"checks": {}}

    # ── 1. 单节点 from_env / 注册 ─────────────────────────────────
    pool = GPUPool(
        nodes=[
            GPUNode(
                node_id="gpu-0",
                comfyui_url="http://127.0.0.1:8000",
                available_vram=32,
            )
        ]
    )
    reset_gpu_pool_for_tests(pool)
    results["checks"]["single_node_register"] = {
        "nodes": len(pool.nodes),
        "url": pool.nodes[0].comfyui_url,
    }
    if len(pool.nodes) != 1:
        issues.append("expected 1 node")

    # ── 2. 空闲分配 + mark_busy / mark_free ───────────────────────
    node = pool.get_available_node(required_vram=24, prefer_short=True)
    if node.node_id != "gpu-0":
        issues.append(f"unexpected node {node.node_id}")
    pool.mark_busy("gpu-0", task_id="t-long", estimated_duration=300)
    if not pool.nodes[0].busy or pool.nodes[0].current_task_id != "t-long":
        issues.append("mark_busy failed")
    if pool.nodes[0].estimated_free_at is None:
        issues.append("estimated_free_at missing")

    # 全忙时仍返回节点（最早空闲）
    busy_pick = pool.get_available_node(required_vram=8, estimated_duration_sec=30)
    if busy_pick.node_id != "gpu-0":
        issues.append("busy pool should still return gpu-0")

    pool.mark_free("gpu-0")
    if pool.nodes[0].busy or pool.nodes[0].current_task_id is not None:
        issues.append("mark_free failed")
    results["checks"]["busy_free"] = "ok"

    # ── 3. 多节点：短任务优先空闲节点 ─────────────────────────────
    pool2 = GPUPool(
        nodes=[
            GPUNode("gpu-a", "http://127.0.0.1:8000", 32, busy=True, current_task_id="L1",
                    estimated_free_at=datetime.now(timezone.utc)),
            GPUNode("gpu-b", "http://127.0.0.1:8001", 32, busy=False),
        ]
    )
    short_node = pool2.get_available_node(
        required_vram=16, estimated_duration_sec=30, prefer_short=True
    )
    if short_node.node_id != "gpu-b":
        issues.append(f"short task should prefer free gpu-b, got {short_node.node_id}")
    results["checks"]["short_prefers_free"] = short_node.node_id

    # ── 4. estimate_duration + queue bucket ────────────────────────
    cases = [
        ("flux-dev", {}, 30, "short_queue"),
        ("hidream", {}, 30, "short_queue"),
        ("wan-2.6", {"duration": 5, "steps": 4}, None, "short_queue"),
        ("hunyuan-video-1.5", {"width": 1280, "height": 720, "steps": 50}, 480, "long_queue"),
        (
            "hunyuan-video-1.5",
            {"width": 1280, "height": 720, "use_distilled": True},
            120,
            "long_queue",
        ),
        ("video-enhance-seedvr2", {}, 60, "short_queue"),
    ]
    duration_results = []
    for mid, params, expect_sec, expect_q in cases:
        sec = estimate_duration(mid, params)
        q = estimate_queue_bucket(mid, params)
        row = {"model": mid, "params": params, "sec": sec, "queue": q}
        duration_results.append(row)
        if expect_sec is not None and sec != expect_sec:
            # distilled 720p: 480//4=120 → long_queue（边界 ≥120）
            if mid == "hunyuan-video-1.5" and params.get("use_distilled") and sec == 120:
                pass
            else:
                issues.append(f"duration {mid} {params} => {sec}, want {expect_sec}")
        if q != expect_q:
            # 蒸馏 120s 边界：queue_bucket 用 < 120 → long
            if expect_q == "long_queue" and sec >= SHORT_TASK_THRESHOLD_SEC and q == "long_queue":
                pass
            elif q != expect_q:
                issues.append(f"queue {mid} => {q}, want {expect_q}")
        if queue_bucket(sec) != q:
            issues.append(f"queue_bucket mismatch for {mid}")

    # wan 动态：至少 short（通常 <120）
    wan_sec = estimate_duration("wan-2.6", {"duration": 5, "steps": 4})
    if wan_sec >= SHORT_TASK_THRESHOLD_SEC:
        issues.append(f"wan estimate unexpectedly long: {wan_sec}")

    results["checks"]["estimate_duration"] = duration_results
    results["checks"]["threshold"] = SHORT_TASK_THRESHOLD_SEC

    # ── 5. from_env 逗号分隔 ──────────────────────────────────────
    import os

    os.environ["COMFYUI_NODES"] = "http://127.0.0.1:8000,http://127.0.0.1:8001"
    env_pool = GPUPool.from_env()
    if len(env_pool.nodes) != 2:
        issues.append(f"from_env expected 2 nodes, got {len(env_pool.nodes)}")
    results["checks"]["from_env"] = [n.comfyui_url for n in env_pool.nodes]
    reset_gpu_pool_for_tests(pool)

    ok = not issues
    payload = {
        "ok": ok,
        "issues": issues,
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
