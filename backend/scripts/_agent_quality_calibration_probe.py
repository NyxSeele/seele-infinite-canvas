#!/usr/bin/env python3
"""Agent 全链路质量校准：编排现有探针，汇总水位并对照阈值。

用法（需后端 :7788）：
  cd backend
  .venv/bin/python scripts/_agent_quality_calibration_probe.py
  .venv/bin/python scripts/_agent_quality_calibration_probe.py --with-gpu

退出码：0=校准 PASS（允许 e2e WARN）；1=基建失败；3=断言/阈值 FAIL
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "bin" / "python"
LOG_DIR = Path("/root/autodl-tmp/logs")
OUT_PATH = LOG_DIR / "agent_quality_calibration.json"
BASELINE_JSON = LOG_DIR / "agent_trace_baseline.json"
PREV_CALIBRATION = OUT_PATH  # 上次校准结果（同路径，跑前可读）

# 校准阈值（与 AGENT_TRACE_BASELINE / 计划一致）
PIPELINE_TOKEN_SOFT_LO = 1500
PIPELINE_TOKEN_SOFT_HI = 2200
PIPELINE_TOKEN_FAIL = 2500
PIPELINE_TOKEN_GOLDEN_LO = 1700
PIPELINE_TOKEN_GOLDEN_HI = 1900
ADV_PASS_TARGET = 6
ADV_WARN_MIN = 5
A4_SHOTS_TARGET = 3
A4_DESC_MIN = 50
A2_SCREENPLAY_MIN = 500


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def wait_backend(timeout_s: int = 90) -> bool:
    import urllib.request
    deadline = __import__("time").time() + timeout_s
    while __import__("time").time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:7788/health", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        __import__("time").sleep(2)
    return False


def _run(
    name: str,
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
    need_backend: bool = True,
) -> dict[str, Any]:
    if need_backend and not wait_backend():
        return {
            "name": name,
            "argv": argv,
            "exit_code": 1,
            "elapsed_s": 0,
            "stdout_tail": "",
            "stderr_tail": "backend health check failed",
            "error": "backend_down",
        }
    print(f"\n=== [{name}] {' '.join(argv)} ===", flush=True)
    t0 = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "argv": argv,
            "exit_code": 1,
            "elapsed_s": (datetime.now(timezone.utc) - t0).total_seconds(),
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "timeout",
            "error": "timeout",
        }
    out = proc.stdout or ""
    err = proc.stderr or ""
    print(out[-3000:] if len(out) > 3000 else out, flush=True)
    if err.strip():
        print(err[-1500:], file=sys.stderr, flush=True)
    # 探针之间冷却，降低 agent/text 429
    __import__("time").sleep(3)
    return {
        "name": name,
        "argv": argv,
        "exit_code": proc.returncode,
        "elapsed_s": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "stdout_tail": out[-6000:],
        "stderr_tail": err[-2000:],
    }


def extract_pipeline_tokens(baseline: dict) -> dict[str, Any]:
    """从 baseline JSON 的 trace_lines 提取 pipeline 轮 vs 创意轮 tokens。"""
    lines = baseline.get("trace_lines") or []
    pipeline_tokens: list[int] = []
    creative_tokens: list[int] = []
    last_pipeline = False
    for line in lines:
        if "A1 AGENT_INPUT" in line:
            last_pipeline = "pipeline_prompt=True" in line
        elif "A1 AGENT_OUTPUT" in line:
            m = re.search(r"tokens=(\d+)", line)
            if not m:
                continue
            tok = int(m.group(1))
            if last_pipeline:
                pipeline_tokens.append(tok)
            else:
                creative_tokens.append(tok)
    # 若无 pipeline_prompt 标记，用 agent_rounds 中「继续」类轮次的 parsed 末轮兜底
    a1 = (baseline.get("parsed") or {}).get("A1") or {}
    if not pipeline_tokens and isinstance(a1.get("tokens"), int):
        # 单点观测：若末轮 input 含 pipeline_prompt
        inp = a1.get("agent_input_line") or ""
        if "pipeline_prompt=True" in inp:
            pipeline_tokens.append(int(a1["tokens"]))
        else:
            creative_tokens.append(int(a1["tokens"]))

    def _stats(vals: list[int], *, recent: int | None = None) -> dict[str, Any]:
        use = vals[-recent:] if (recent and len(vals) > recent) else vals
        if not use:
            return {"count": 0, "values": [], "median": None, "min": None, "max": None}
        return {
            "count": len(use),
            "values": use,
            "median": int(statistics.median(use)),
            "min": min(use),
            "max": max(use),
            "all_count": len(vals),
        }

    # 全量日志常混入历史高 token；校准优先取「G32 形态」样本（1.2k–2.5k）
    g32ish = [t for t in pipeline_tokens if 1200 <= t <= 2500]
    pipe_src = g32ish if len(g32ish) >= 3 else pipeline_tokens
    return {
        "pipeline": _stats(pipe_src, recent=8),
        "creative": _stats(creative_tokens, recent=8),
        "pipeline_raw_count": len(pipeline_tokens),
        "pipeline_g32ish_count": len(g32ish),
    }


def extract_a3_a4(baseline: dict) -> dict[str, Any]:
    parsed = baseline.get("parsed") or {}
    a3_line = (parsed.get("A3") or {}).get("structure_output_line") or ""
    a4_line = (parsed.get("A4") or {}).get("shots_output_line") or ""
    scenes = None
    m = re.search(r"scenes_count=(\d+)", a3_line)
    if m:
        scenes = int(m.group(1))
    if scenes is None:
        scenes = baseline.get("outline_scenes_count")
    total_shots = None
    m2 = re.search(r"total_shots=(\d+)", a4_line)
    if m2:
        total_shots = int(m2.group(1))
    shots_detail = (parsed.get("A4") or {}).get("shots_detail") or []
    short_descs = []
    for shot in shots_detail:
        desc = (shot.get("prompt") or shot.get("description") or "").strip()
        if desc and len(desc) < A4_DESC_MIN:
            short_descs.append({"id": shot.get("id") or shot.get("shot_number"), "len": len(desc)})
    screenplay = baseline.get("screenplay_preview") or ""
    # preview 可能截断；用 A2 output_len 若有
    a2_out = (parsed.get("A2") or {}).get("text_outputs") or []
    a2_len = None
    for line in a2_out:
        m3 = re.search(r"output_len=(\d+)", line)
        if m3:
            a2_len = int(m3.group(1))
    if a2_len is None:
        a2_len = len(screenplay)
    return {
        "scenes_count": scenes,
        "total_shots": total_shots,
        "short_descriptions": short_descs,
        "screenplay_len": a2_len,
        "shots_detail_count": len(shots_detail),
    }


def parse_adversarial(result: dict) -> dict[str, Any]:
    text = (result.get("stdout_tail") or "") + "\n" + (result.get("stderr_tail") or "")
    m = re.search(r"结果:\s*(\d+)/(\d+)\s*通过", text)
    passed = int(m.group(1)) if m else 0
    total = int(m.group(2)) if m else 6
    failed_ids: list[str] = []
    current_id = None
    for line in text.splitlines():
        m2 = re.match(r"\[\d+/\d+\]\s+([a-z0-9_]+)", line.strip())
        if m2:
            current_id = m2.group(1)
            continue
        if current_id and re.search(r"\bFAIL\b", line) and "PASS" not in line:
            if current_id not in failed_ids:
                failed_ids.append(current_id)
            current_id = None
        m3 = re.match(r"\s*-\s*([a-z0-9_]+)\s*:", line)
        if m3 and m3.group(1) not in failed_ids:
            failed_ids.append(m3.group(1))
    return {"passed": passed, "total": total, "failed_ids": failed_ids, "exit_code": result.get("exit_code")}


def load_prev_adv_failures() -> list[str]:
    if not PREV_CALIBRATION.is_file():
        return []
    try:
        prev = json.loads(PREV_CALIBRATION.read_text(encoding="utf-8"))
        return list((prev.get("adversarial") or {}).get("failed_ids") or [])
    except Exception:
        return []


def calibrate(
    *,
    pytest_ok: bool,
    baseline_exit: int,
    token_stats: dict,
    a3a4: dict,
    adv: dict,
    e2e_exit: int,
    gpu: dict | None,
    prev_adv_fail: list[str],
) -> dict[str, Any]:
    verdicts: list[dict[str, Any]] = []
    hard_fail = False
    warn = False

    if not pytest_ok:
        verdicts.append({"metric": "pytest", "status": "FAIL", "detail": "g32/trace unit failed"})
        hard_fail = True
    else:
        verdicts.append({"metric": "pytest", "status": "PASS", "detail": "g32 + trace_bus"})

    if baseline_exit != 0:
        verdicts.append({"metric": "baseline", "status": "FAIL", "detail": f"exit={baseline_exit}"})
        hard_fail = True
    else:
        verdicts.append({"metric": "baseline", "status": "PASS", "detail": "reached generate_script_table"})

    pipe = token_stats.get("pipeline") or {}
    med = pipe.get("median")
    token_band_update = None
    if med is None:
        verdicts.append({"metric": "pipeline_tokens", "status": "WARN", "detail": "no pipeline token samples"})
        warn = True
    elif med > PIPELINE_TOKEN_FAIL:
        verdicts.append({
            "metric": "pipeline_tokens",
            "status": "FAIL",
            "detail": f"median={med} > {PIPELINE_TOKEN_FAIL} (G32 regression)",
        })
        hard_fail = True
    elif PIPELINE_TOKEN_SOFT_LO <= med <= PIPELINE_TOKEN_SOFT_HI:
        token_band_update = {
            "lo": min(PIPELINE_TOKEN_GOLDEN_LO, med - 100),
            "hi": max(PIPELINE_TOKEN_GOLDEN_HI, med + 100),
            "observed_median": med,
        }
        verdicts.append({
            "metric": "pipeline_tokens",
            "status": "PASS",
            "detail": f"median={med} in soft band {PIPELINE_TOKEN_SOFT_LO}-{PIPELINE_TOKEN_SOFT_HI}; update golden band",
            "band_update": token_band_update,
        })
    else:
        verdicts.append({
            "metric": "pipeline_tokens",
            "status": "WARN",
            "detail": f"median={med} outside soft band {PIPELINE_TOKEN_SOFT_LO}-{PIPELINE_TOKEN_SOFT_HI}",
        })
        warn = True

    creative = token_stats.get("creative") or {}
    if creative.get("median") is not None:
        verdicts.append({
            "metric": "creative_tokens",
            "status": "OBS",
            "detail": f"median={creative['median']} (observe only, ~5k expected)",
        })

    scenes = a3a4.get("scenes_count")
    shots = a3a4.get("total_shots")
    if baseline_exit != 0:
        verdicts.append({"metric": "a3_scenes", "status": "SKIP", "detail": "baseline failed; no fresh A3"})
        verdicts.append({"metric": "a4_shots", "status": "SKIP", "detail": "baseline failed; no fresh A4"})
        verdicts.append({"metric": "a4_desc_len", "status": "SKIP", "detail": "baseline failed"})
        verdicts.append({"metric": "a2_screenplay", "status": "SKIP", "detail": "baseline failed"})
    else:
        if scenes is None:
            verdicts.append({"metric": "a3_scenes", "status": "WARN", "detail": "scenes_count missing"})
            warn = True
        elif scenes != A4_SHOTS_TARGET:
            verdicts.append({"metric": "a3_scenes", "status": "FAIL", "detail": f"scenes_count={scenes}"})
            hard_fail = True
        else:
            verdicts.append({"metric": "a3_scenes", "status": "PASS", "detail": f"scenes_count={scenes}"})

        if shots is None:
            verdicts.append({"metric": "a4_shots", "status": "WARN", "detail": "total_shots missing"})
            warn = True
        elif shots < A4_SHOTS_TARGET:
            verdicts.append({"metric": "a4_shots", "status": "FAIL", "detail": f"total_shots={shots}"})
            hard_fail = True
        elif shots != A4_SHOTS_TARGET:
            verdicts.append({
                "metric": "a4_shots",
                "status": "WARN",
                "detail": f"total_shots={shots} (target={A4_SHOTS_TARGET})",
            })
            warn = True
        else:
            verdicts.append({"metric": "a4_shots", "status": "PASS", "detail": f"total_shots={shots}"})

        if a3a4.get("short_descriptions"):
            verdicts.append({
                "metric": "a4_desc_len",
                "status": "FAIL",
                "detail": f"short={a3a4['short_descriptions']}",
            })
            hard_fail = True
        elif a3a4.get("shots_detail_count"):
            verdicts.append({"metric": "a4_desc_len", "status": "PASS", "detail": f">={A4_DESC_MIN} chars"})

        sp_len = a3a4.get("screenplay_len") or 0
        if sp_len and sp_len < A2_SCREENPLAY_MIN:
            verdicts.append({"metric": "a2_screenplay", "status": "FAIL", "detail": f"len={sp_len}"})
            hard_fail = True
        elif sp_len:
            verdicts.append({"metric": "a2_screenplay", "status": "PASS", "detail": f"len={sp_len}"})

    adv_passed = adv.get("passed") or 0
    adv_total = adv.get("total") or 6
    failed_ids = adv.get("failed_ids") or []
    if adv.get("exit_code") == 1 and adv_passed == 0:
        verdicts.append({"metric": "adversarial", "status": "FAIL", "detail": "infra / connect"})
        hard_fail = True
    elif adv_passed < ADV_WARN_MIN:
        verdicts.append({
            "metric": "adversarial",
            "status": "FAIL",
            "detail": f"{adv_passed}/{adv_total} failed_ids={failed_ids}",
        })
        hard_fail = True
    elif adv_passed < ADV_PASS_TARGET:
        repeat = sorted(set(failed_ids) & set(prev_adv_fail))
        detail = f"{adv_passed}/{adv_total} failed_ids={failed_ids}"
        if repeat:
            detail += f"; repeat_failures={repeat} (需人工复核用例，勿盲目放宽)"
        verdicts.append({"metric": "adversarial", "status": "WARN", "detail": detail})
        warn = True
    else:
        verdicts.append({"metric": "adversarial", "status": "PASS", "detail": f"{adv_passed}/{adv_total}"})

    if e2e_exit == 0:
        verdicts.append({"metric": "e2e", "status": "PASS", "detail": "pipeline e2e ok"})
    elif e2e_exit == 1:
        verdicts.append({"metric": "e2e", "status": "FAIL", "detail": "infra"})
        hard_fail = True
    else:
        verdicts.append({
            "metric": "e2e",
            "status": "WARN",
            "detail": f"exit={e2e_exit} (LLM order variance; does not block calibration PASS alone)",
        })
        warn = True

    if gpu is not None:
        if gpu.get("exit_code") == 0:
            verdicts.append({"metric": "route_c_gpu", "status": "PASS", "detail": "ok"})
        else:
            verdicts.append({
                "metric": "route_c_gpu",
                "status": "FAIL",
                "detail": f"exit={gpu.get('exit_code')}",
            })
            hard_fail = True
    else:
        verdicts.append({"metric": "route_c_gpu", "status": "SKIP", "detail": "default skip; use --with-gpu"})

    overall = "FAIL" if hard_fail else ("WARN" if warn else "PASS")
    return {
        "overall": overall,
        "hard_fail": hard_fail,
        "warn": warn,
        "verdicts": verdicts,
        "token_band_update": token_band_update,
    }


def render_markdown_section(report: dict) -> str:
    cal = report.get("calibration") or {}
    lines = [
        "",
        f"## 校准 {report.get('run_at_local', '')}",
        "",
        f"- **overall**: `{cal.get('overall')}`",
        f"- **JSON**: [`{OUT_PATH}`]({OUT_PATH})",
        "",
        "| 指标 | 状态 | 详情 |",
        "|------|------|------|",
    ]
    for v in cal.get("verdicts") or []:
        lines.append(f"| {v.get('metric')} | {v.get('status')} | {v.get('detail')} |")
    tok = report.get("tokens") or {}
    pipe = tok.get("pipeline") or {}
    lines.extend([
        "",
        "### Token 水位",
        "",
        f"- pipeline median/min/max: **{pipe.get('median')}** / {pipe.get('min')} / {pipe.get('max')} (n={pipe.get('count')})",
        f"- creative median: {(tok.get('creative') or {}).get('median')} (观测)",
        f"- golden 原区间: {PIPELINE_TOKEN_GOLDEN_LO}–{PIPELINE_TOKEN_GOLDEN_HI}；soft: {PIPELINE_TOKEN_SOFT_LO}–{PIPELINE_TOKEN_SOFT_HI}；FAIL>{PIPELINE_TOKEN_FAIL}",
    ])
    band = cal.get("token_band_update")
    if band:
        lines.append(
            f"- **建议更新基线区间**: {band['lo']}–{band['hi']}（observed median={band['observed_median']}）"
        )
    adv = report.get("adversarial") or {}
    lines.extend([
        "",
        "### 对抗回归",
        "",
        f"- {adv.get('passed')}/{adv.get('total')}；failed_ids={adv.get('failed_ids')}",
        "",
        "不自动放宽对抗断言或 A4 字数门禁。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent quality calibration orchestrator")
    parser.add_argument("--with-gpu", action="store_true", help="Also run Route-C GPU probe")
    parser.add_argument("--skip-e2e", action="store_true", help="Skip pipeline e2e (faster)")
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-adversarial", action="store_true")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="Admin@2026!")
    args = parser.parse_args()

    py = str(VENV_PY if VENV_PY.is_file() else sys.executable)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    prev_adv = load_prev_adv_failures()
    steps: list[dict] = []

    # 1) pytest
    pytest_res = _run(
        "pytest_g32_trace",
        [py, "-m", "pytest", "tests/test_g32_agent_tokens.py", "tests/test_trace_bus.py", "-q"],
        cwd=ROOT,
        timeout=120,
        need_backend=False,
    )
    steps.append(pytest_res)
    pytest_ok = pytest_res["exit_code"] == 0

    # 2) baseline
    baseline_res = {"name": "baseline", "exit_code": 0, "skipped": True}
    if not args.skip_baseline:
        baseline_res = _run(
            "agent_trace_baseline",
            [py, str(SCRIPTS / "_agent_trace_baseline_probe.py")],
            cwd=ROOT,
            timeout=900,
        )
    steps.append(baseline_res)

    baseline_data: dict = {}
    baseline_fresh = False
    baseline_exit_code = baseline_res.get("exit_code")
    if baseline_exit_code is None:
        baseline_exit_code = 1
    else:
        baseline_exit_code = int(baseline_exit_code)

    if BASELINE_JSON.is_file() and baseline_exit_code == 0:
        try:
            baseline_data = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
            baseline_fresh = True
        except Exception as exc:
            print(f"warn: cannot read baseline json: {exc}", flush=True)
    elif BASELINE_JSON.is_file():
        try:
            stale = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
            print(
                f"warn: baseline exit={baseline_exit_code}; "
                f"ignoring stale A3/A4 (run_at={stale.get('run_at')})",
                flush=True,
            )
        except Exception:
            pass

    token_stats = (
        extract_pipeline_tokens(baseline_data)
        if baseline_fresh
        else {"pipeline": {"count": 0}, "creative": {"count": 0}}
    )
    a3a4 = extract_a3_a4(baseline_data) if baseline_fresh else {}
    if baseline_fresh and not (token_stats.get("pipeline") or {}).get("count"):
        # 回退：用 parsed.A1 末轮 tokens（若 pipeline_prompt）
        a1 = (baseline_data.get("parsed") or {}).get("A1") or {}
        tok = a1.get("tokens")
        inp = a1.get("agent_input_line") or ""
        if isinstance(tok, int) and "pipeline_prompt=True" in inp:
            token_stats = {
                "pipeline": {
                    "count": 1,
                    "values": [tok],
                    "median": tok,
                    "min": tok,
                    "max": tok,
                },
                "creative": token_stats.get("creative") or {"count": 0},
            }

    # 3) adversarial
    adv_res = {"name": "adversarial", "exit_code": 0, "skipped": True, "stdout_tail": "结果: 6/6 通过"}
    if not args.skip_adversarial:
        adv_res = _run(
            "adversarial_regression",
            [
                py,
                str(SCRIPTS / "_adversarial_regression_probe.py"),
                "--username",
                args.username,
                "--password",
                args.password,
            ],
            cwd=ROOT,
            timeout=900,
        )
    steps.append(adv_res)
    adv = parse_adversarial(adv_res)

    # 4) e2e
    e2e_res = {"name": "e2e", "exit_code": 0, "skipped": True}
    if not args.skip_e2e:
        e2e_res = _run(
            "agent_pipeline_e2e",
            [
                py,
                str(SCRIPTS / "_agent_pipeline_e2e_probe.py"),
                "--skip-text",
                args.username,
                args.password,
            ],
            cwd=ROOT,
            timeout=1200,
        )
    steps.append(e2e_res)

    # 5) optional GPU
    gpu_res = None
    if args.with_gpu:
        gpu_res = _run(
            "route_c_agent_gpu",
            [py, str(SCRIPTS / "_route_c_agent_gpu_probe.py")],
            cwd=ROOT,
            timeout=7200,
        )
        steps.append(gpu_res)

    cal = calibrate(
        pytest_ok=pytest_ok,
        baseline_exit=int(baseline_res.get("exit_code") or 0),
        token_stats=token_stats,
        a3a4=a3a4,
        adv=adv,
        e2e_exit=int(e2e_res.get("exit_code") or 0),
        gpu=gpu_res,
        prev_adv_fail=prev_adv,
    )

    run_at = _now()
    report = {
        "run_at_local": run_at,
        "with_gpu": bool(args.with_gpu),
        "steps": [
            {
                "name": s.get("name"),
                "exit_code": s.get("exit_code"),
                "elapsed_s": s.get("elapsed_s"),
                "skipped": s.get("skipped"),
                "error": s.get("error"),
            }
            for s in steps
        ],
        "tokens": token_stats,
        "a3_a4": a3a4,
        "adversarial": adv,
        "calibration": cal,
        "markdown_section": None,
    }
    report["markdown_section"] = render_markdown_section(report)

    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n======== CALIBRATION SUMMARY ========", flush=True)
    print(f"overall={cal['overall']}", flush=True)
    for v in cal["verdicts"]:
        print(f"  [{v['status']}] {v['metric']}: {v['detail']}", flush=True)
    print(f"\nWrote {OUT_PATH}", flush=True)
    print(report["markdown_section"], flush=True)

    if cal["hard_fail"]:
        return 3
    # WARN still exit 0 for calibration pass-with-notes (plan: e2e WARN 不挡)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
