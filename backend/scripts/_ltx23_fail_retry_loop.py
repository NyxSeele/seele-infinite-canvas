#!/usr/bin/env python3
"""LTX-2.3 自跑测试循环：冒烟 + GPU 矩阵，失败自动修/降参重试。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND_ROOT / "scripts"
LOG_DIR = Path("/root/autodl-tmp/logs")
STATUS_OUT = LOG_DIR / "ltx23_loop_status.json"
COMFY_LOG = Path("/root/autodl-tmp/logs/comfyui0.out.log")
BACKEND_LOG = Path("/root/autodl-tmp/logs/backend.out.log")
MAX_ROUNDS = 4
DEFAULT_INTERVAL_SEC = 60


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 7200) -> subprocess.CompletedProcess:
    print(f"[run] {' '.join(cmd)}", flush=True)
    return subprocess.run(
        cmd,
        cwd=str(cwd or BACKEND_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _http_ok(url: str) -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=10) as resp:
            return int(getattr(resp, "status", 200)) == 200
    except Exception:
        return False


def _tail_errors(path: Path, *, lines: int = 80) -> list[str]:
    if not path.is_file():
        return []
    hits = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]:
        low = line.lower()
        if any(k in low for k in ("error", "exception", "oom", "cuda", "failed", "traceback")):
            hits.append(line.strip())
    return hits[-lines:]


def _looks_like_oom(errors: list[str]) -> bool:
    blob = "\n".join(errors).lower()
    return any(k in blob for k in ("out of memory", "oom", "cuda error", "alloc"))


def try_fix_smoke() -> list[str]:
    actions: list[str] = []
    if not _http_ok("http://127.0.0.1:8000/system_stats"):
        cp = _run(
            ["/usr/bin/supervisorctl", "-c", "/etc/supervisor/supervisord.conf", "restart", "comfyui0"],
            timeout=120,
        )
        actions.append(f"restart comfyui0 exit={cp.returncode}")
        time.sleep(20)
    if not _http_ok("http://127.0.0.1:7788/docs"):
        cp = _run(
            ["/usr/bin/supervisorctl", "-c", "/etc/supervisor/supervisord.conf", "restart", "aistudio-backend"],
            timeout=120,
        )
        actions.append(f"restart backend exit={cp.returncode}")
        time.sleep(10)
    sync = _run(
        [
            str(BACKEND_ROOT / ".venv/bin/python"),
            "-c",
            "from services.registered_model_sync import sync_registered_models; "
            "print(sync_registered_models(only={'ltx23-i2av'}, verbose=True))",
        ],
        timeout=120,
    )
    actions.append(f"sync_registered_models exit={sync.returncode}")
    if sync.stdout.strip():
        actions.append(sync.stdout.strip()[-500:])
    return actions


def run_acceptance() -> tuple[bool, dict]:
    out = LOG_DIR / "ltx23_acceptance.json"
    cp = _run(
        [str(BACKEND_ROOT / ".venv/bin/python"), str(SCRIPTS / "_ltx23_acceptance_probe.py"), "--json"],
        timeout=300,
    )
    report: dict = {}
    if out.is_file():
        try:
            report = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
    passed = cp.returncode == 0 and bool(report.get("pass"))
    return passed, report


def run_gpu_matrix(
    *,
    width: int | None,
    height: int | None,
    resolution: str,
    resume: bool = False,
    from_case: str | None = None,
) -> tuple[bool, dict]:
    cmd = [
        str(BACKEND_ROOT / ".venv/bin/python"),
        str(SCRIPTS / "_ltx23_gpu_matrix.py"),
        "--resolution",
        resolution,
        "--duration",
        "5",
    ]
    if width is not None and height is not None:
        cmd.extend(["--width", str(width), "--height", str(height)])
    if resume:
        cmd.append("--resume")
    if from_case:
        cmd.extend(["--from-case", from_case])
    cp = _run(cmd, timeout=7200)
    out = LOG_DIR / "ltx23_gpu_matrix.json"
    report: dict = {"exit_code": cp.returncode}
    if out.is_file():
        try:
            report = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {"parse_error": True}
    if cp.stderr:
        report["stderr_tail"] = cp.stderr[-2000:]
    if cp.stdout:
        report["stdout_tail"] = cp.stdout[-2000:]
    if cp.returncode != 0 and "pass" not in report:
        report["pass"] = False
        report["crash"] = True
    passed = cp.returncode == 0 and bool(report.get("pass"))
    return passed, report


def write_status(payload: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATUS_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_cycle(*, max_rounds: int, smoke_once: bool = False, resume_gpu: bool = False) -> tuple[bool, list[dict]]:
    """单轮周期：最多 max_rounds 次重试，返回 (是否通过, 历史)。"""
    history: list[dict] = []
    reduced = False
    resolution = "720P"
    width: int | None = None
    height: int | None = None
    last_errors: list[str] = []
    smoke_cached: bool | None = None

    for round_idx in range(1, max_rounds + 1):
        round_rec: dict = {"round": round_idx, "smoke": {}, "gpu": {}, "fixes": []}

        if smoke_once and smoke_cached is True:
            smoke_pass, smoke_report = True, {"pass": True, "skipped": True}
            round_rec["smoke"] = {"pass": True, "skipped": True}
        else:
            smoke_pass, smoke_report = run_acceptance()
            round_rec["smoke"] = {"pass": smoke_pass, "report": smoke_report}
            if not smoke_pass:
                round_rec["fixes"].extend(try_fix_smoke())
                smoke_pass, smoke_report = run_acceptance()
                round_rec["smoke"]["pass_after_fix"] = smoke_pass
                round_rec["smoke"]["report_after_fix"] = smoke_report
            smoke_cached = smoke_pass
        if not smoke_pass:
            last_errors = smoke_report.get("no_audio_issues", []) + smoke_report.get(
                "with_audio_issues", []
            )
            history.append(round_rec)
            write_status(
                {
                    "cycle_pass": False,
                    "round": round_idx,
                    "phase": "smoke",
                    "pass": False,
                    "next_action": "retry_smoke",
                    "history": history[-10:],
                    "errors": last_errors,
                }
            )
            continue

        gpu_pass, gpu_report = run_gpu_matrix(
            width=width,
            height=height,
            resolution=resolution,
            resume=resume_gpu,
        )
        round_rec["gpu"] = {
            "pass": gpu_pass,
            "report_summary": {
                "required_failures": gpu_report.get("required_failures"),
                "tables": gpu_report.get("tables"),
            },
        }
        if gpu_pass:
            history.append(round_rec)
            return True, history

        last_errors = _tail_errors(COMFY_LOG) + _tail_errors(BACKEND_LOG)
        if gpu_report.get("crash"):
            last_errors.append(
                gpu_report.get("stderr_tail")
                or gpu_report.get("stdout_tail")
                or "gpu matrix crashed"
            )
        for row in gpu_report.get("tables") or []:
            if row.get("error"):
                last_errors.append(f"{row.get('id')}: {row.get('error')}")
        round_rec["errors"] = last_errors[-20:]

        if _looks_like_oom(last_errors) and not reduced:
            reduced = True
            width, height = 848, 480
            resolution = "480P"
            round_rec["fixes"].append("downgrade to 848x480 after OOM")
            history.append(round_rec)
            write_status(
                {
                    "cycle_pass": False,
                    "round": round_idx,
                    "phase": "gpu_retry",
                    "pass": False,
                    "next_action": "retry_gpu_reduced",
                    "history": history[-10:],
                    "errors": last_errors[-20:],
                }
            )
            continue

        if not _http_ok("http://127.0.0.1:8000/system_stats"):
            round_rec["fixes"].extend(try_fix_smoke())
        history.append(round_rec)
        write_status(
            {
                "cycle_pass": False,
                "round": round_idx,
                "phase": "gpu",
                "pass": False,
                "next_action": "retry_gpu",
                "history": history[-10:],
                "errors": last_errors[-20:],
            }
        )

    return False, history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rounds", type=int, default=MAX_ROUNDS)
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="通过后继续循环（默认单次跑完即停）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SEC,
        help="连续模式下每轮间隔秒数（默认 60）",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="GPU 矩阵断点续跑（跳过已 PASS/SKIP case）",
    )
    args = parser.parse_args()

    cycle_no = 0
    smoke_once = False
    while True:
        cycle_no += 1
        print(f"[cycle] start #{cycle_no}", flush=True)
        write_status(
            {
                "mode": "continuous" if args.continuous else "once",
                "cycle": cycle_no,
                "phase": "running",
                "pass": None,
                "resume_gpu": bool(args.resume),
            }
        )

        passed, history = run_cycle(
            max_rounds=args.max_rounds,
            smoke_once=smoke_once,
            resume_gpu=bool(args.resume),
        )
        if passed:
            smoke_once = True
            write_status(
                {
                    "mode": "continuous" if args.continuous else "once",
                    "cycle": cycle_no,
                    "phase": "cycle_pass",
                    "pass": True,
                    "history": history[-10:],
                    "gpu_matrix": str(LOG_DIR / "ltx23_gpu_matrix.json"),
                    "acceptance": str(LOG_DIR / "ltx23_acceptance.json"),
                    "next_action": "sleep_and_rerun" if args.continuous else "stop",
                }
            )
            print("LTX23_LOOP_PASS_ROUND", flush=True)
            if not args.continuous:
                print("LTX23_LOOP_DONE", flush=True)
                return 0
        else:
            write_status(
                {
                    "mode": "continuous" if args.continuous else "once",
                    "cycle": cycle_no,
                    "phase": "cycle_fail",
                    "pass": False,
                    "history": history[-10:],
                    "next_action": "sleep_and_rerun" if args.continuous else "stop",
                }
            )
            print("LTX23_LOOP_FAIL_ROUND", flush=True)
            if not args.continuous:
                print("LTX23_LOOP_GAVE_UP", flush=True)
                return 1

        if not args.continuous:
            break

        print(f"[cycle] sleep {args.interval}s before next run", flush=True)
        time.sleep(max(5, min(60, int(args.interval))))


if __name__ == "__main__":
    raise SystemExit(main())
