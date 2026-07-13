#!/usr/bin/env python3
"""G30 phash 对照：route_b 三镜 flux-pulid vs 已有 flux-dev 基线。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _route_b_batch_probe as route_b
from services.image_consistency import check_consistency

OUT = Path("/root/autodl-tmp/logs/g30_phash_compare.json")
FACE = Path("/tmp/face_ref.png")
BASELINE = Path("/root/autodl-tmp/logs/route_c_results.json")


def run_images(model: str, face_path: Path | None) -> list[dict]:
    route_b.IMAGE_MODEL = model
    route_b.REFERENCE_FACE_URL = None
    shots: list[dict] = []
    with httpx.Client(timeout=180.0) as client:
        token = route_b.login(client)
        if model == "flux-pulid" and face_path and face_path.is_file():
            route_b.REFERENCE_FACE_URL = route_b.upload_reference_face(
                client, token, str(face_path)
            )
        prior: list[dict] = []
        prev_url: str | None = None
        for shot in route_b.SHOTS:
            trace_id = __import__("uuid").uuid4()
            built = route_b.build_shot(
                client, token, shot=shot, prior_shots=prior,
                has_prev_image=bool(prev_url), trace_id=str(trace_id),
            )
            positive = (built.get("prompt") or "").strip()
            display = (built.get("display_prompt") or shot["description"]).strip()
            ref, denoise = route_b.resolve_image_reference(
                built=built, prev_image_url=prev_url,
                reference_face_url=route_b.REFERENCE_FACE_URL,
            )
            submitted = route_b.submit_image(
                client, token, prompt=positive, display_prompt=display,
                trace_id=str(trace_id), reference_image=ref, denoise=denoise,
            )
            finished = route_b.poll_task(client, token, submitted["task_id"])
            result_url = route_b.task_result_url(finished)
            row = {
                "shot_id": shot["id"],
                "status": finished.get("status"),
                "result_url": result_url,
                "model": model,
            }
            shots.append(row)
            if finished.get("status") != "completed" or not result_url:
                raise RuntimeError(f"shot {shot['id']} failed: {finished}")
            prev_url = result_url
            prior.append({"shot_number": shot["shot_number"], "description": shot["description"]})
    return shots


def main() -> int:
    baseline_phash = []
    if BASELINE.is_file():
        baseline_phash = json.loads(BASELINE.read_text()).get("consistency_phash") or []

    print("=== flux-pulid 3-shot GPU ===", flush=True)
    pulid_shots = run_images("flux-pulid", FACE)
    with httpx.Client(timeout=60.0) as client:
        token = route_b.login(client)
        pulid_phash = check_consistency(
            [s["result_url"] for s in pulid_shots if s.get("result_url")],
            token=token,
        )

    out = {
        "flux_dev_baseline_phash": baseline_phash,
        "flux_pulid_phash": pulid_phash.get("consistency_phash"),
        "flux_pulid_threshold": pulid_phash.get("consistency_threshold"),
        "flux_pulid_shots": pulid_shots,
        "comparison_note": "lower phash distance => better identity consistency",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}", flush=True)
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
