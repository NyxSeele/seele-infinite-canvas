"""
粘贴剧本判定探针 — API 冒烟 + E1 弱剧本边界回归。

用法（需后端 :7788 已启动，且 DASHSCOPE_API_KEY 可用）：
  cd backend
  $env:SEED_ADMIN_PASSWORD="…"
  .\\.venv\\Scripts\\python.exe scripts\\_paste_script_checklist_probe.py

  # 仅跑 E1 稳定性（改 prompt_intent.py 后优先跑这条）
  .\\.venv\\Scripts\\python.exe scripts\\_paste_script_checklist_probe.py --only e1

  # 调整重复次数（默认 8）
  .\\.venv\\Scripts\\python.exe scripts\\_paste_script_checklist_probe.py --e1-runs 5

  # 输出完整 JSON（含每次 classify 明细）
  .\\.venv\\Scripts\\python.exe scripts\\_paste_script_checklist_probe.py --json

E1 回归背景（勿删 — 下次改 CLASSIFY_SYSTEM 时靠这段回忆「测什么、为何这样测」）：
  - 清单 E1：弱剧本信号 — 刚过 400 字门槛、有对白但无「第一场」/时间轴
  - 2026-06-25 补 few-shot **前**（各 1 次）：399→screenplay conf=0.9，401→chat conf=0.6（差 2 字结论相反）
  - 补 few-shot **后**（各 8 次）：16/16 均为 chat conf=0.6，399 与 401 不再「来回跳戏」
  - 为何 399/401：紧贴 PASTE_HINT_MIN=400 两侧，最容易暴露字数敏感漂移
  - 为何重复 8 次：平衡 LLM 调用成本与方差观测；不追求 100% 但要求同长度内 intent 一致、两字之间 intent 一致
  - 期望锚点：CLASSIFY_SYSTEM 边界示例 A → intent=chat，confidence 约 0.55~0.65
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

BASE = os.environ.get("API_BASE", "http://127.0.0.1:7788")
USER = os.environ.get("PROBE_USER", "admin")
PASSWORD = os.environ.get("PROBE_PASSWORD", os.environ.get("SEED_ADMIN_PASSWORD", ""))

# ── E1 弱剧本边界回归（永久用例，改 prompt_intent.py 后必跑）────────────────
E1_WEAK_LENGTHS = (399, 401)
E1_STABILITY_RUNS_DEFAULT = 8
E1_EXPECTED_INTENT = "chat"
E1_FORBIDDEN_INTENT = "screenplay"
E1_CONFIDENCE_MIN = 0.5
E1_CONFIDENCE_MAX = 0.75


def req(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=90) as resp:
        return json.loads(resp.read().decode())


def login() -> str:
    if not PASSWORD:
        raise SystemExit("Set PROBE_PASSWORD or SEED_ADMIN_PASSWORD")
    out = req("POST", "/api/auth/login", {"username_or_email": USER, "password": PASSWORD})
    return out["access_token"]


def classify(token: str, text: str, context: str = "text", mode: str | None = None) -> dict:
    return req(
        "POST",
        "/api/prompt/classify-intent",
        {"text": text, "context": context, "current_text_mode": mode},
        token,
    )


def plain(n: int) -> str:
    return "这是一段普通创作描述文字，用于测试阈值边界。"[:n].ljust(n, "字")


def weak_screenplay(n: int) -> str:
    """弱剧本样例：重复对白撑字数，无场次/时间轴标记（清单 E1）。"""
    base = (
        "小明走进房间，对小华说：「你今天怎么了？」小华沉默片刻说：「没什么。」"
        "窗外下着雨，两人对坐良久。这段对白重复出现以撑满字数，但没有第一场或分场标题。"
    )
    return (base * ((n // len(base)) + 1))[:n]


def strong_screenplay() -> str:
    return """第一场 内景 客厅 日
小明：（推门）我回来了。
小华：你怎么这么晚？
【00:00-00:05】镜头从门口推进。
第二场 外景 街道 夜
旁白：雨越下越大。
小明：我们走吧。
第三场 内景 卧室 夜
小华：明天再说。
第四场 内景 厨房 晨
小明：早餐好了。""" * 8


def run_f1_fallback() -> dict:
    import asyncio
    from unittest.mock import patch

    from services.prompt_intent import classify_user_intent

    async def _run():
        with patch("services.prompt_intent._call_llm", side_effect=RuntimeError("llm down")):
            return await classify_user_intent(strong_screenplay(), context="image")

    return {"result": asyncio.run(_run())}


def run_e1_stability(
    token: str,
    *,
    runs: int = E1_STABILITY_RUNS_DEFAULT,
    sleep_s: float = 0.25,
) -> dict[str, Any]:
    """E1：399/401 弱剧本各重复 classify，汇总方差与断言。"""
    rows: list[dict[str, Any]] = []
    for run_idx in range(1, runs + 1):
        for chars in E1_WEAK_LENGTHS:
            t0 = time.time()
            result = classify(token, weak_screenplay(chars), context="text")
            rows.append(
                {
                    "run": run_idx,
                    "chars": chars,
                    "intent": result.get("intent"),
                    "confidence": round(float(result.get("confidence") or 0), 3),
                    "ms": int((time.time() - t0) * 1000),
                }
            )
            if sleep_s > 0:
                time.sleep(sleep_s)

    summary: dict[str, Any] = {}
    for chars in E1_WEAK_LENGTHS:
        subset = [r for r in rows if r["chars"] == chars]
        intents = Counter(r["intent"] for r in subset)
        confs = [r["confidence"] for r in subset]
        summary[str(chars)] = {
            "intent_counts": dict(intents),
            "confidence_min": min(confs),
            "confidence_max": max(confs),
            "confidence_avg": round(sum(confs) / len(confs), 3),
            "stable_single_intent": len(intents) == 1,
            "dominant_intent": intents.most_common(1)[0][0] if intents else None,
        }

    issues = evaluate_e1(summary, rows)
    return {
        "id": "e1_weak_screenplay_stability",
        "ok": len(issues) == 0,
        "runs_per_length": runs,
        "lengths": list(E1_WEAK_LENGTHS),
        "expected_intent": E1_EXPECTED_INTENT,
        "rows": rows,
        "summary": summary,
        "issues": issues,
    }


def evaluate_e1(summary: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    """机器可读断言 — 仿对抗性回归探针。"""
    issues: list[str] = []
    label = "E1 弱剧本 399/401"

    for chars in E1_WEAK_LENGTHS:
        key = str(chars)
        block = summary.get(key) or {}
        counts: dict[str, int] = block.get("intent_counts") or {}
        total = sum(counts.values()) or len([r for r in rows if r["chars"] == chars])
        expected_hits = counts.get(E1_EXPECTED_INTENT, 0)
        forbidden_hits = counts.get(E1_FORBIDDEN_INTENT, 0)

        if not block.get("stable_single_intent"):
            issues.append(f"{label} {chars}字: intent 不一致 {counts}")

        if expected_hits != total:
            issues.append(
                f"{label} {chars}字: 期望 {expected_hits}/{total} 次为 {E1_EXPECTED_INTENT!r}，"
                f"实际 {counts}"
            )

        if forbidden_hits > 0:
            issues.append(
                f"{label} {chars}字: 不应判为 {E1_FORBIDDEN_INTENT!r}，出现 {forbidden_hits} 次"
            )

        conf_min = block.get("confidence_min")
        conf_max = block.get("confidence_max")
        if conf_min is not None and conf_max is not None:
            if conf_min < E1_CONFIDENCE_MIN or conf_max > E1_CONFIDENCE_MAX:
                issues.append(
                    f"{label} {chars}字: confidence 超出 [{E1_CONFIDENCE_MIN}, {E1_CONFIDENCE_MAX}]，"
                    f"实测 [{conf_min}, {conf_max}]"
                )

    dom_399 = (summary.get("399") or {}).get("dominant_intent")
    dom_401 = (summary.get("401") or {}).get("dominant_intent")
    if dom_399 and dom_401 and dom_399 != dom_401:
        issues.append(
            f"{label}: 399 与 401 主导 intent 不一致（{dom_399!r} vs {dom_401!r}）—「差两字跳戏」回归"
        )

    return issues


def run_smoke_cases(token: str) -> list[dict[str, Any]]:
    """清单 A/F/C 等 API 单次冒烟（非 E1 重复）。"""
    results: list[dict[str, Any]] = []

    def run(case_id: str, fn):
        try:
            out = fn()
            results.append({"id": case_id, "ok": True, **out})
        except Exception as e:
            results.append({"id": case_id, "ok": False, "error": str(e)})

    run("f1_llm_fallback", run_f1_fallback)
    run("api_plain_79", lambda: {"result": classify(token, plain(79))})
    run("api_plain_81", lambda: {"result": classify(token, plain(81))})
    run("api_weak_399_once", lambda: {"result": classify(token, weak_screenplay(399))})
    run("api_weak_401_once", lambda: {"result": classify(token, weak_screenplay(401))})
    run("api_screenplay_img", lambda: {"result": classify(token, strong_screenplay(), context="image")})
    run("api_screenplay_vid", lambda: {"result": classify(token, strong_screenplay(), context="video")})
    run("api_screenplay_mode", lambda: {
        "result": classify(token, strong_screenplay(), context="text", mode="screenplay")
    })
    return results


def print_e1_report(e1: dict[str, Any]) -> None:
    print("E1 弱剧本边界稳定性回归")
    print(f"  样例: weak_screenplay(399/401)，各 {e1['runs_per_length']} 次 classify")
    print(f"  期望: intent={E1_EXPECTED_INTENT!r}，confidence∈[{E1_CONFIDENCE_MIN}, {E1_CONFIDENCE_MAX}]")
    print()
    for chars in E1_WEAK_LENGTHS:
        s = e1["summary"][str(chars)]
        counts = s["intent_counts"]
        print(
            f"  {chars}字: {counts} | conf avg={s['confidence_avg']} "
            f"[{s['confidence_min']}, {s['confidence_max']}] | "
            f"{'稳定' if s['stable_single_intent'] else '漂移'}"
        )
    if e1["ok"]:
        print("\n  E1 PASS")
    else:
        print("\n  E1 FAIL:")
        for issue in e1["issues"]:
            print(f"    - {issue}")


def main() -> int:
    parser = argparse.ArgumentParser(description="粘贴剧本判定探针（冒烟 + E1 回归）")
    parser.add_argument(
        "--only",
        choices=("all", "e1", "smoke"),
        default="all",
        help="仅跑 E1 稳定性 / 仅冒烟 / 全部（默认）",
    )
    parser.add_argument(
        "--e1-runs",
        type=int,
        default=E1_STABILITY_RUNS_DEFAULT,
        metavar="N",
        help=f"E1 每个字数重复次数（默认 {E1_STABILITY_RUNS_DEFAULT}）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 打印完整结果（含 E1 每次明细）",
    )
    args = parser.parse_args()

    try:
        token = login()
    except urllib.error.URLError as exc:
        print(f"错误：无法连接 {BASE}，请先启动后端（{exc}）")
        return 1

    payload: dict[str, Any] = {"api_base": BASE}
    all_ok = True

    if args.only in ("all", "smoke"):
        payload["smoke"] = run_smoke_cases(token)
        smoke_fail = [r for r in payload["smoke"] if not r.get("ok")]
        if smoke_fail:
            all_ok = False

    if args.only in ("all", "e1"):
        print(f"粘贴剧本探针 — E1 稳定性（各 {args.e1_runs} 次）…", flush=True)
        e1 = run_e1_stability(token, runs=max(1, args.e1_runs))
        payload["e1"] = e1
        if not e1["ok"]:
            all_ok = False
        if not args.json:
            print_e1_report(e1)

    if args.only == "smoke" and not args.json:
        smoke = payload.get("smoke") or []
        ok_n = sum(1 for r in smoke if r.get("ok"))
        print(f"冒烟: {ok_n}/{len(smoke)} 通过")
        for r in smoke:
            if not r.get("ok"):
                print(f"  FAIL {r['id']}: {r.get('error')}")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not all_ok:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
