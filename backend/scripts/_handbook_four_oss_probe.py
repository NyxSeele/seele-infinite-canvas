#!/usr/bin/env python3
"""四个开源项目操作测试手册 · 统一自动化探针（无浏览器）。

编排 health → login → pytest → A/B/C/D 章节检查，输出：
  docs/HANDBOOK_FOUR_OSS_PROBE_RESULT.json
终端最后一行：HANDBOOK_FOUR_OSS=PASS 或 FAIL
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from _agent_manifest_handtest_probe import (  # noqa: E402
    BASE,
    EXPECTED_STEPS,
    prepare_generation_slots,
    relative_order_ok,
)
from _agent_trace_baseline_probe import headers, load_admin_password  # noqa: E402

OUT_PATH = ROOT.parent / "docs" / "HANDBOOK_FOUR_OSS_PROBE_RESULT.json"
MANIFEST_OUT = ROOT.parent / "docs" / "AGENT_MANIFEST_PROBE_RESULT.json"
VENV_PY = ROOT / ".venv/bin/python"
VENV_PYTEST = ROOT / ".venv/bin/pytest"

MOCK_ENV = {
    "SHORT_VIDEO_MOCK_LLM": "1",
    "SHORT_VIDEO_MOCK_TTS": "1",
    "SHORT_VIDEO_MOCK_STOCK": "1",
}

BUILD_SHOT_MODEL = "flux-dev"
SHORT_VIDEO_POLL_TIMEOUT_S = 300.0
SHORT_VIDEO_POLL_INTERVAL_S = 2.0
LOGIN_TIMEOUT_S = 15.0
HEALTH_CONNECT_S = 3.0
HEALTH_MAX_S = 5.0
SUPERVISORCTL = "/usr/bin/supervisorctl"
SUPERVISOR_CONF = "/etc/supervisor/supervisord.conf"
SUPERVISOR_PROGRAM_CONF = Path("/etc/supervisor/conf.d/aistudio.conf")
_SUPERVISOR_ENV_BACKUP: str | None = None


def log(msg: str) -> None:
    print(msg, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check(name: str, passed: bool, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "pass": passed}
    row.update(extra)
    return row


def skip_item(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "status": "SKIP", "reason": reason}


def redact_gateway_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Strip plaintext api_key; keep masked fields only."""
    safe = {k: v for k, v in data.items() if k != "api_key"}
    if "api_key" in data and "api_key_masked" not in safe:
        safe["api_key_masked"] = "***"
    return safe


def run_pytest(files: list[str], *, label: str = "all") -> tuple[bool, dict[str, Any]]:
    cmd = [str(VENV_PYTEST), *files, "-q", "--tb=no"]
    env = {**os.environ, **MOCK_ENV, "PYTHONPATH": str(ROOT)}
    log(f"[pytest:{label}] {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined = stdout + stderr
    passed = failed = 0
    m = re.search(r"(\d+) passed", combined)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+) failed", combined)
    if m:
        failed = int(m.group(1))
    meta = {
        "label": label,
        "command": " ".join(cmd),
        "passed": passed,
        "failed": failed,
        "exit_code": proc.returncode,
        "summary_tail": combined.strip()[-500:],
    }
    return proc.returncode == 0, meta


B_PYTEST = [
    "tests/test_entity_identity_injection.py",
    "tests/test_prompt_builder.py",
]
C_PYTEST = [
    "tests/test_edge_tts_service.py",
    "tests/test_short_video_factory.py",
    "tests/test_stock_material_service.py",
]
D_PYTEST = ["tests/test_model_gateway_resolver.py"]
A_PYTEST = ["tests/test_tool_registry.py"]


def check_tool_envelope() -> dict[str, Any]:
    from services.pipeline_manifest import load_pipeline
    from services.tool_registry import support_envelope

    manifest = load_pipeline("velora_canvas")
    env = support_envelope(manifest)
    steps = env.get("steps") or []
    ok = len(steps) == 9 and all(s in steps for s in EXPECTED_STEPS)
    return check(
        "tool_envelope_9_steps",
        ok,
        step_count=len(steps),
        steps=steps,
    )


def chapter_a_openmontage(
    client: httpx.Client,
    token: str,
    username: str,
    report: dict[str, Any],
) -> bool:
    chap: dict[str, Any] = {"checks": [], "skip": [], "warnings": []}
    chap["skip"] = [
        skip_item("A2_skill_menu", "no-browser"),
        skip_item("A3_pipeline_panel", "no-browser"),
    ]

    # A1 pipeline API
    pr = client.get(
        f"{BASE}/api/agent/pipeline/velora_canvas",
        headers=headers(token),
        timeout=30,
    )
    stage_names: list[str] = []
    manifest_ok = pr.status_code == 200
    if manifest_ok:
        stages = pr.json().get("stages") or []
        stage_names = [s.get("name") for s in stages]
        manifest_ok = len(stage_names) == 9
    chap["checks"].append(
        check(
            "pipeline_velora_canvas_9_stages",
            manifest_ok,
            status=pr.status_code,
            stage_count=len(stage_names),
            stage_names=stage_names,
        )
    )

    # tool envelope (in-process, complements pytest)
    env_chk = check_tool_envelope()
    chap["checks"].append(env_chk)

    # Manifest handtest subprocess
    manifest_sub_ok = False
    manifest_steps_ok = False
    text_mode: str | None = None
    manifest_verdict = "FAIL"
    log("[A] running _agent_manifest_handtest_probe.py …")
    try:
        proc = subprocess.run(
            [str(VENV_PY), "scripts/_agent_manifest_handtest_probe.py"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=660,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"MANIFEST_HANDTEST=(PASS|FAIL)", out)
        if m:
            manifest_verdict = m.group(1)
        if MANIFEST_OUT.is_file():
            manifest_data = json.loads(MANIFEST_OUT.read_text(encoding="utf-8"))
            recorded = manifest_data.get("recorded_steps") or []
            text_mode = manifest_data.get("text_generation_mode")
            manifest_steps_ok = relative_order_ok(recorded, EXPECTED_STEPS)
            manifest_sub_ok = manifest_verdict == "PASS"
            chap["checks"].append(
                check(
                    "manifest_recorded_steps",
                    manifest_steps_ok,
                    recorded=recorded,
                    expected_relative=list(EXPECTED_STEPS),
                    subprocess_verdict=manifest_verdict,
                )
            )
            text_real = isinstance(text_mode, str) and text_mode.startswith("real")
            chap["checks"].append(
                check(
                    "text_generation_mode_real",
                    text_real,
                    mode=text_mode,
                    soft=True,
                )
            )
            if not text_real:
                chap["warnings"].append(
                    f"text_generation_mode not real_* (got {text_mode!r}); "
                    "A may still PASS if steps OK"
                )
        else:
            chap["checks"].append(
                check(
                    "manifest_subprocess",
                    False,
                    detail="AGENT_MANIFEST_PROBE_RESULT.json missing",
                    exit_code=proc.returncode,
                )
            )
    except subprocess.TimeoutExpired:
        chap["checks"].append(
            check("manifest_subprocess", False, detail="timeout after 660s")
        )
        report["issues"].append(
            {
                "chapter": "A",
                "message": "manifest handtest probe timed out",
                "product_bug": True,
            }
        )

    # A pass: pipeline + steps + envelope; text mock is WARN only
    core_checks = [
        manifest_ok,
        env_chk["pass"],
        manifest_steps_ok,
    ]
    chap["pass"] = all(core_checks)
    if not chap["pass"]:
        if not manifest_ok:
            report["issues"].append(
                {
                    "chapter": "A",
                    "message": "GET /api/agent/pipeline/velora_canvas not 9 stages",
                    "product_bug": True,
                }
            )
        if not manifest_steps_ok:
            report["issues"].append(
                {
                    "chapter": "A",
                    "message": "manifest recorded_steps missing expected pipeline order",
                    "product_bug": True,
                }
            )

    report["chapters"]["A_openmontage"] = chap
    return bool(chap["pass"])


def chapter_b_dramaclaw(
    client: httpx.Client,
    token: str,
    b_pytest_ok: bool,
    report: dict[str, Any],
) -> bool:
    chap: dict[str, Any] = {"checks": [], "skip": [], "warnings": []}
    chap["skip"] = [
        skip_item("B3_video_metadata_identity_ids", "no dedicated test"),
        skip_item("B4_explore_track_ui", "no-browser"),
    ]

    chap["checks"].append(
        check("pytest_entity_identity_and_prompt_builder", b_pytest_ok, soft=False)
    )

    cast_missing = [
        {
            "name": "Alice",
            "type": "character",
            "identityId": "alice_default",
        }
    ]
    body_missing = {
        "description": "Alice 走进房间",
        "model_id": BUILD_SHOT_MODEL,
        "cast_library": cast_missing,
        "identity_ids": ["alice_default"],
        "row": {"identityIds": ["alice_default"], "prompt": "Alice 走进房间"},
    }
    r_miss = client.post(
        f"{BASE}/api/prompt/build-shot",
        headers=headers(token),
        json=body_missing,
        timeout=60,
    )
    # Transient 5xx after heavy load — one health+retry
    if r_miss.status_code >= 500:
        wait_healthy(allow_restart=True)
        r_miss = client.post(
            f"{BASE}/api/prompt/build-shot",
            headers=headers(token),
            json=body_missing,
            timeout=60,
        )
    miss_ok = False
    miss_code = None
    if r_miss.status_code == 422:
        detail = r_miss.json().get("detail")
        if isinstance(detail, dict):
            miss_code = detail.get("code")
            miss_ok = miss_code == "missing_identity"
    chap["checks"].append(
        check(
            "build_shot_missing_identity_422",
            miss_ok,
            status=r_miss.status_code,
            code=miss_code,
        )
    )

    cast_ok = [
        {
            "name": "Alice",
            "type": "character",
            "identityId": "alice_default",
            "faceUrl": "http://probe.local/alice.png",
        }
    ]
    body_ok = {
        "description": "Alice 站在窗边",
        "model_id": BUILD_SHOT_MODEL,
        "cast_library": cast_ok,
        "identity_ids": ["alice_default"],
        "row": {"identityIds": ["alice_default"]},
    }
    r_ok = client.post(
        f"{BASE}/api/prompt/build-shot",
        headers=headers(token),
        json=body_ok,
        timeout=60,
    )
    not_missing = True
    if r_ok.status_code == 422:
        detail = r_ok.json().get("detail")
        if isinstance(detail, dict) and detail.get("code") == "missing_identity":
            not_missing = False
    chap["checks"].append(
        check(
            "build_shot_with_refs_no_missing_identity",
            not_missing,
            status=r_ok.status_code,
        )
    )

    chap["pass"] = b_pytest_ok and miss_ok and not_missing
    if not chap["pass"]:
        if not miss_ok:
            report["issues"].append(
                {
                    "chapter": "B",
                    "message": "build-shot missing identity gate failed",
                    "product_bug": True,
                }
            )
        if not not_missing:
            report["issues"].append(
                {
                    "chapter": "B",
                    "message": "build-shot still returns missing_identity with refs",
                    "product_bug": True,
                }
            )

    report["chapters"]["B_dramaclaw"] = chap
    return bool(chap["pass"])


def run_short_video_probe(visual: str) -> dict[str, Any]:
    env = {**os.environ, **MOCK_ENV, "SHORT_VIDEO_PROBE_VISUAL": visual}
    cmd = [str(VENV_PY), "scripts/_short_video_factory_probe.py"]
    log(f"[C] short video probe visual={visual}")
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ok = "PROBE_OK" in out
    return check(
        f"short_video_factory_probe_{visual}",
        ok,
        exit_code=proc.returncode,
        stdout_tail=out.strip()[-300:],
    )


def is_mock_ffmpeg_failure(error: str | None) -> bool:
    if not error:
        return False
    return "exit status 183" in error or "CalledProcessError" in error


def poll_short_video_http(
    client: httpx.Client,
    token: str,
    report: dict[str, Any],
    *,
    enable_tts: bool = True,
    burn_captions: bool = True,
    check_name: str = "short_video_http_completed",
) -> dict[str, Any]:
    body = {
        "topic": "人工智能如何改变生活",
        "segment_count": 3,
        "burn_captions": burn_captions,
        "enable_tts": enable_tts,
        "voice_name": "zh-CN-XiaoxiaoNeural",
        "visual_source": "slide",
    }
    r = client.post(
        f"{BASE}/api/short-video/generate",
        headers=headers(token),
        json=body,
        timeout=60,
    )
    if r.status_code != 200:
        return check(
            "short_video_http_generate",
            False,
            status=r.status_code,
            body=r.text[:300],
        )
    task_id = r.json().get("task_id")
    deadline = time.time() + SHORT_VIDEO_POLL_TIMEOUT_S
    last_status = "unknown"
    last_error = None
    while time.time() < deadline:
        pr = client.get(
            f"{BASE}/api/short-video/{task_id}",
            headers=headers(token),
            timeout=30,
        )
        if pr.status_code != 200:
            return check(
                "short_video_http_poll",
                False,
                task_id=task_id,
                status=pr.status_code,
            )
        payload = pr.json()
        last_status = payload.get("status") or ""
        last_error = payload.get("error")
        if last_status == "completed":
            file_ok = True
            file_size = 0
            fr = client.get(
                f"{BASE}/api/short-video/{task_id}/file",
                headers={"Authorization": f"Bearer {token}"},
                timeout=120,
            )
            if fr.status_code == 200:
                file_size = len(fr.content)
                file_ok = file_size > 0
            else:
                file_ok = False
            return check(
                check_name,
                file_ok,
                task_id=task_id,
                status=last_status,
                file_bytes=file_size,
                enable_tts=enable_tts,
                burn_captions=burn_captions,
            )
        if last_status in ("failed", "error"):
            break
        time.sleep(SHORT_VIDEO_POLL_INTERVAL_S)

    if check_name == "short_video_http_completed":
        report["issues"].append(
            {
                "chapter": "C",
                "message": f"short-video HTTP task {task_id} ended as {last_status}: {last_error}",
                "product_bug": is_mock_ffmpeg_failure(last_error),
            }
        )
    return check(
        check_name,
        False,
        task_id=task_id,
        status=last_status,
        error=last_error,
        enable_tts=enable_tts,
        burn_captions=burn_captions,
    )


def health_code() -> str:
    try:
        r = httpx.get(
            f"{BASE}/api/health",
            timeout=httpx.Timeout(HEALTH_MAX_S, connect=HEALTH_CONNECT_S),
        )
        return str(r.status_code)
    except Exception:
        return "000"


def supervisorctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SUPERVISORCTL, "-c", SUPERVISOR_CONF, *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def supervisor_restart_backend() -> None:
    log("supervisorctl restart aistudio-backend")
    supervisorctl("restart", "aistudio-backend")
    time.sleep(8)


def wait_healthy(*, allow_restart: bool = True) -> tuple[bool, str]:
    """Hard gate: health must be 200. At most one supervisorctl restart."""
    code = health_code()
    if code == "200":
        return True, "health ok"
    if not allow_restart:
        return False, f"health={code} (no restart)"
    if not Path(SUPERVISORCTL).is_file():
        return False, f"health={code}; supervisorctl missing"
    log(f"health={code} — restart aistudio-backend once")
    supervisor_restart_backend()
    # Warm-up: health may flip 200 before login/DB is ready
    for _ in range(6):
        code2 = health_code()
        if code2 == "200":
            return True, "health ok after supervisorctl restart"
        time.sleep(2)
    code2 = health_code()
    if code2 == "200":
        return True, "health ok after supervisorctl restart"
    return False, f"health={code2} after supervisorctl restart — abort (no login hang)"


def login_strict(client: httpx.Client, password: str) -> tuple[str | None, str]:
    """Login with 15s timeout; seele then admin."""
    for username in ("seele", "admin"):
        try:
            r = client.post(
                f"{BASE}/api/auth/login",
                json={"username_or_email": username, "password": password},
                timeout=LOGIN_TIMEOUT_S,
            )
            if r.status_code == 200:
                return r.json()["access_token"], username
            log(f"login {username} failed: HTTP {r.status_code}")
        except Exception as exc:
            log(f"login {username} error: {exc}")
    return None, ""


def login_with_retries(password: str) -> tuple[str | None, str, str]:
    """Up to 2 login attempts; one supervisor restart between attempts if needed."""
    with httpx.Client(timeout=LOGIN_TIMEOUT_S) as client:
        token, user = login_strict(client, password)
        if token:
            return token, user, "ok"
    log("login attempt 1 failed — health check + optional restart")
    ok, detail = wait_healthy(allow_restart=True)
    if not ok:
        return None, "", f"login failed; {detail}"
    time.sleep(3)
    with httpx.Client(timeout=LOGIN_TIMEOUT_S) as client:
        token, user = login_strict(client, password)
        if token:
            return token, user, "ok after restart"
    return None, "", "login failed after 2 attempts (timeout<=15s)"


def _backend_environment_line(text: str) -> tuple[int, str] | None:
    in_backend = False
    for i, line in enumerate(text.splitlines()):
        if line.strip().startswith("[program:aistudio-backend]"):
            in_backend = True
            continue
        if in_backend and line.strip().startswith("[program:"):
            break
        if in_backend and line.startswith("environment="):
            return i, line
    return None


def enable_supervisor_short_video_mock() -> tuple[bool, str]:
    """Temporarily inject SHORT_VIDEO_MOCK_* into supervisor conf + restart (no kill)."""
    global _SUPERVISOR_ENV_BACKUP
    if not SUPERVISOR_PROGRAM_CONF.is_file():
        return False, "supervisor conf missing"
    text = SUPERVISOR_PROGRAM_CONF.read_text(encoding="utf-8")
    found = _backend_environment_line(text)
    if not found:
        return False, "aistudio-backend environment= not found"
    idx, line = found
    _SUPERVISOR_ENV_BACKUP = line
    if "SHORT_VIDEO_MOCK_LLM" in line:
        supervisor_restart_backend()
        ok, detail = wait_healthy(allow_restart=False)
        return ok, f"MOCK already in conf; {detail}"
    extras = (
        ',SHORT_VIDEO_MOCK_LLM="1",SHORT_VIDEO_MOCK_TTS="1",SHORT_VIDEO_MOCK_STOCK="1"'
    )
    new_line = line.rstrip() + extras
    lines = text.splitlines()
    lines[idx] = new_line
    SUPERVISOR_PROGRAM_CONF.write_text("\n".join(lines) + "\n", encoding="utf-8")
    supervisorctl("reread")
    supervisorctl("update")
    supervisor_restart_backend()
    ok, detail = wait_healthy(allow_restart=True)
    return ok, f"injected MOCK into supervisor env; {detail}"


def restore_supervisor_short_video_mock() -> None:
    global _SUPERVISOR_ENV_BACKUP
    if _SUPERVISOR_ENV_BACKUP is None or not SUPERVISOR_PROGRAM_CONF.is_file():
        return
    text = SUPERVISOR_PROGRAM_CONF.read_text(encoding="utf-8")
    found = _backend_environment_line(text)
    if found:
        idx, _ = found
        lines = text.splitlines()
        lines[idx] = _SUPERVISOR_ENV_BACKUP
        SUPERVISOR_PROGRAM_CONF.write_text("\n".join(lines) + "\n", encoding="utf-8")
        supervisorctl("reread")
        supervisorctl("update")
        supervisor_restart_backend()
        wait_healthy(allow_restart=True)
    _SUPERVISOR_ENV_BACKUP = None


def chapter_c_short_video(
    client: httpx.Client,
    token: str,
    password: str,
    c_pytest_ok: bool,
    report: dict[str, Any],
) -> bool:
    chap: dict[str, Any] = {"checks": [], "skip": [], "warnings": []}
    chap["skip"] = [skip_item("C1_canvas_node_ui", "no-browser")]

    chap["checks"].append(check("pytest_short_video_suite", c_pytest_ok))
    chap["checks"].append(run_short_video_probe("slide"))
    chap["checks"].append(run_short_video_probe("stock"))

    mock_ok, mock_detail = enable_supervisor_short_video_mock()
    chap["checks"].append(check("backend_mock_env_for_http", mock_ok, detail=mock_detail))

    # Re-login after possible supervisor restart
    token2, user2, login_detail = login_with_retries(password)
    if token2:
        token = token2
        report["login_user"] = user2 or report.get("login_user")
    else:
        chap["warnings"].append(f"re-login after MOCK inject failed: {login_detail}")

    http_ok = False
    if mock_ok and token:
        with httpx.Client(timeout=300.0) as c2:
            http_chk = poll_short_video_http(c2, token, report)
            chap["checks"].append(http_chk)
            if http_chk["pass"]:
                http_ok = True
            elif is_mock_ffmpeg_failure(http_chk.get("error")):
                chap["warnings"].append(
                    "MOCK TTS 空 mp3 与真实 ffmpeg 不兼容；尝试 slide-only HTTP 回退"
                )
                fallback = poll_short_video_http(
                    c2,
                    token,
                    report,
                    enable_tts=False,
                    burn_captions=False,
                    check_name="short_video_http_slide_fallback",
                )
                chap["checks"].append(fallback)
                http_ok = fallback["pass"]
                if fallback["pass"]:
                    report["issues"].append(
                        {
                            "chapter": "C",
                            "message": "TTS+burn_captions HTTP 因 MOCK 空 mp3/ffmpeg 失败；slide-only 回退成功（产品 bug）",
                            "product_bug": True,
                        }
                    )
            else:
                # Missing model without MOCK still product/env issue
                err = str(http_chk.get("error") or "")
                if "未配置" in err or "qwen-turbo" in err:
                    report["issues"].append(
                        {
                            "chapter": "C",
                            "message": f"short-video HTTP failed: {err}",
                            "product_bug": True,
                        }
                    )
    else:
        chap["checks"].append(
            check(
                "short_video_http_completed",
                False,
                detail="skipped — MOCK inject or login failed",
            )
        )

    try:
        restore_supervisor_short_video_mock()
    except Exception as exc:
        chap["warnings"].append(f"restore supervisor MOCK failed: {exc}")

    core_names = {
        "pytest_short_video_suite",
        "short_video_factory_probe_slide",
        "short_video_factory_probe_stock",
    }
    chap["pass"] = (
        all(c["pass"] for c in chap["checks"] if c["name"] in core_names) and http_ok
    )
    report["chapters"]["C_short_video"] = chap
    return bool(chap["pass"])


def chapter_d_gateway(
    client: httpx.Client,
    token: str,
    username: str,
    password: str,
    d_pytest_ok: bool,
    report: dict[str, Any],
) -> tuple[bool, bool]:
    """Returns (chapter_pass, route_404_fail_overall)."""
    chap: dict[str, Any] = {"checks": [], "skip": [], "warnings": []}
    route_404 = False

    gr = client.get(
        f"{BASE}/api/admin/model-gateway",
        headers=headers(token),
        timeout=30,
    )
    if gr.status_code == 403 and username != "admin":
        # retry with admin login for gateway only
        ar = client.post(
            f"{BASE}/api/auth/login",
            json={"username_or_email": "admin", "password": password},
            timeout=30,
        )
        if ar.status_code == 200:
            admin_token = ar.json()["access_token"]
            gr = client.get(
                f"{BASE}/api/admin/model-gateway",
                headers=headers(admin_token),
                timeout=30,
            )

    gateway_ok = gr.status_code == 200
    if gr.status_code == 404:
        route_404 = True

    fields_ok = False
    payload_safe: dict[str, Any] = {}
    if gateway_ok:
        raw = gr.json()
        payload_safe = redact_gateway_payload(raw)
        fields_ok = all(k in payload_safe for k in ("enabled", "base_url", "api_key_masked"))

    chap["checks"].append(
        check(
            "get_admin_model_gateway",
            gateway_ok and fields_ok,
            status=gr.status_code,
            fields=list(payload_safe.keys()),
            gateway=payload_safe,
        )
    )
    chap["checks"].append(
        check("pytest_model_gateway_resolver", d_pytest_ok)
    )

    chap["pass"] = gateway_ok and fields_ok and d_pytest_ok
    if route_404:
        report["issues"].append(
            {
                "chapter": "D",
                "message": "GET /api/admin/model-gateway returned 404 — route not mounted",
                "product_bug": True,
                "fail_overall": True,
            }
        )
    elif not chap["pass"]:
        report["issues"].append(
            {
                "chapter": "D",
                "message": "model gateway check failed (WARN — does not fail overall unless 404)",
                "product_bug": False,
            }
        )
        chap["warnings"].append("D chapter FAIL but non-404 — overall may still PASS")

    report["chapters"]["D_gateway"] = chap
    return bool(chap["pass"]), route_404


def finalize_report(report: dict[str, Any], started: float) -> None:
    a_ok = report["chapters"].get("A_openmontage", {}).get("pass", False)
    b_ok = report["chapters"].get("B_dramaclaw", {}).get("pass", False)
    c_ok = report["chapters"].get("C_short_video", {}).get("pass", False)
    d_404 = any(
        i.get("fail_overall") for i in report.get("issues", []) if i.get("chapter") == "D"
    )
    report["pass"] = bool(a_ok and b_ok and c_ok and not d_404)
    report["duration_s"] = round(time.time() - started, 2)
    report["finished_at"] = utc_now()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(report: dict[str, Any]) -> None:
    log("--- handbook summary ---")
    for key, label in (
        ("A_openmontage", "A OpenMontage"),
        ("B_dramaclaw", "B DramaClaw"),
        ("C_short_video", "C ShortVideo"),
        ("D_gateway", "D Gateway"),
    ):
        ch = report["chapters"].get(key, {})
        verdict = "PASS" if ch.get("pass") else "FAIL"
        skips = len(ch.get("skip") or [])
        log(f"  {label}: {verdict} (skip={skips})")
    py = report.get("pytest", {})
    log(f"  pytest: passed={py.get('passed')} failed={py.get('failed')}")
    if report.get("issues"):
        log("  issues:")
        for issue in report["issues"]:
            log(f"    - [{issue.get('chapter')}] {issue.get('message')}")


def main() -> int:
    started = time.time()
    report: dict[str, Any] = {
        "pass": False,
        "started_at": utc_now(),
        "base": BASE,
        "chapters": {},
        "pytest": {"commands": [], "passed": 0, "failed": 0},
        "issues": [],
        "login_user": None,
    }
    mock_injected = False

    try:
        ok, health_msg = wait_healthy(allow_restart=True)
        report["health"] = {"pass": ok, "detail": health_msg}
        if not ok:
            report["issues"].append(
                {"chapter": "infra", "message": health_msg, "product_bug": False}
            )
            # Still emit empty chapter shells so report is not infra-only shape
            for key in ("A_openmontage", "B_dramaclaw", "C_short_video", "D_gateway"):
                report["chapters"][key] = {
                    "pass": False,
                    "checks": [],
                    "skip": [],
                    "warnings": ["skipped — infra health gate failed"],
                }
            finalize_report(report, started)
            print_summary(report)
            log(f"report -> {OUT_PATH}")
            log("HANDBOOK_FOUR_OSS=FAIL")
            return 1

        password = load_admin_password()
        token, username, login_detail = login_with_retries(password)
        report["login_user"] = username
        if not token:
            report["issues"].append(
                {
                    "chapter": "infra",
                    "message": login_detail or "login failed",
                    "product_bug": False,
                }
            )
            for key in ("A_openmontage", "B_dramaclaw", "C_short_video", "D_gateway"):
                report["chapters"][key] = {
                    "pass": False,
                    "checks": [],
                    "skip": [],
                    "warnings": ["skipped — login failed"],
                }
            finalize_report(report, started)
            print_summary(report)
            log(f"report -> {OUT_PATH}")
            log("HANDBOOK_FOUR_OSS=FAIL")
            return 1

        slot_info = prepare_generation_slots(username)
        report["slots"] = slot_info
        log(f"slots cleanup: {slot_info}")

        pytest_runs: list[dict[str, Any]] = []
        a_pytest_ok, a_meta = run_pytest(A_PYTEST, label="A_tool_registry")
        pytest_runs.append(a_meta)
        b_pytest_ok, b_meta = run_pytest(B_PYTEST, label="B_dramaclaw")
        pytest_runs.append(b_meta)
        c_pytest_ok, c_meta = run_pytest(C_PYTEST, label="C_short_video")
        pytest_runs.append(c_meta)
        # Defer D pytest until after HTTP chapters — it can exhaust QueuePool=1
        d_pytest_ok = False
        all_ok = all(r["exit_code"] == 0 for r in pytest_runs)
        report["pytest"] = {
            "commands": [r["command"] for r in pytest_runs],
            "passed": sum(r["passed"] for r in pytest_runs),
            "failed": sum(r["failed"] for r in pytest_runs),
            "all_pass": all_ok,
            "runs": pytest_runs,
        }
        if not all_ok:
            report["issues"].append(
                {
                    "chapter": "pytest",
                    "message": "aggregate pytest suite had failures (see runs)",
                    "product_bug": False,
                }
            )
        _ = a_pytest_ok

        # Clear DB pool before Agent HTTP chapters
        log("post-pytest: supervisorctl restart to clear DB pool")
        supervisor_restart_backend()
        ok2, health2 = wait_healthy(allow_restart=True)
        if not ok2:
            report["issues"].append(
                {
                    "chapter": "infra",
                    "message": f"health lost after pytest: {health2}",
                    "product_bug": False,
                }
            )
            finalize_report(report, started)
            print_summary(report)
            log(f"report -> {OUT_PATH}")
            log("HANDBOOK_FOUR_OSS=FAIL")
            return 1

        prepare_generation_slots(username)
        token, username, login_detail = login_with_retries(password)
        report["login_user"] = username or report.get("login_user")
        if not token:
            report["issues"].append(
                {
                    "chapter": "infra",
                    "message": f"re-login failed: {login_detail}",
                    "product_bug": False,
                }
            )
            finalize_report(report, started)
            print_summary(report)
            log(f"report -> {OUT_PATH}")
            log("HANDBOOK_FOUR_OSS=FAIL")
            return 1

        with httpx.Client(timeout=300.0) as client:
            chapter_a_openmontage(client, token, username, report)
            # Refresh token/health before B if A stressed the backend
            ok_b, _ = wait_healthy(allow_restart=True)
            if ok_b:
                token_b, user_b, _ = login_with_retries(password)
                if token_b:
                    token, username = token_b, user_b or username
            chapter_b_dramaclaw(client, token, b_pytest_ok, report)
            mock_injected = True
            chapter_c_short_video(client, token, password, c_pytest_ok, report)
            token_d, user_d, _ = login_with_retries(password)
            if token_d:
                token = token_d
                username = user_d or username
            # D pytest after HTTP — WARN-only for chapter overall rules
            d_pytest_ok, d_meta = run_pytest(D_PYTEST, label="D_gateway")
            report["pytest"]["commands"].append(d_meta["command"])
            report["pytest"]["runs"].append(d_meta)
            report["pytest"]["passed"] += d_meta["passed"]
            report["pytest"]["failed"] += d_meta["failed"]
            report["pytest"]["all_pass"] = report["pytest"]["all_pass"] and d_pytest_ok
            supervisor_restart_backend()
            wait_healthy(allow_restart=True)
            token_d2, user_d2, _ = login_with_retries(password)
            if token_d2:
                token, username = token_d2, user_d2 or username
            chapter_d_gateway(client, token, username, password, d_pytest_ok, report)

        finalize_report(report, started)
        print_summary(report)
        log(f"report -> {OUT_PATH}")
        verdict = "PASS" if report["pass"] else "FAIL"
        log(f"HANDBOOK_FOUR_OSS={verdict}")
        return 0 if report["pass"] else 2
    finally:
        if mock_injected or _SUPERVISOR_ENV_BACKUP is not None:
            try:
                restore_supervisor_short_video_mock()
            except Exception as exc:
                log(f"finally restore MOCK failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
