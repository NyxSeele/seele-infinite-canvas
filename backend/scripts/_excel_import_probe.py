#!/usr/bin/env python3
"""Excel 导入规则解析探针（西行镇.xlsx + V2 自检/归并验收）。"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.document_import_service import compute_content_hash  # noqa: E402
from services.excel_shot_parser import (  # noqa: E402
    attach_self_check,
    classify_sheet,
    parse_shot_sheet,
    self_check_shot_sheet,
    sheet_plaintext,
    workbook_to_grids_from_path,
)
from services.shot_grouping import build_macro_rows, suggest_groups  # noqa: E402
from services.split_shot_beats import _rule_beats  # noqa: E402

DEFAULT_XLSX = Path(r"c:\Users\小布丁\Desktop\西行镇.xlsx")

# applyBeatsToRow / makeEmptyKeyframe 写入 keyframe 的核心字段集合
APPLY_BEAT_KEYFRAME_FIELDS = frozenset(
    {
        "id",
        "index",
        "label",
        "timeStart",
        "timeEnd",
        "prompt",
        "description",
        "promptEn",
        "promptMentions",
        "referenceImage",
        "resultUrl",
        "status",
        "builtPrompt",
        "compiledPromptPackage",
        "negativePrompt",
        "imageGenNodeId",
        "error",
        "actionNote",
    }
)

MACRO_ROW_FIELDS = frozenset(
    {
        "shotNumber",
        "duration",
        "prompt",
        "keyframes",
        "beatsSplitAt",
        "beatsSplitSource",
    }
)


def _assert_keyframe_fields(keyframes: list[dict]) -> None:
    assert keyframes, "expected non-empty keyframes"
    for kf in keyframes:
        missing = APPLY_BEAT_KEYFRAME_FIELDS - set(kf.keys())
        assert not missing, f"keyframe missing applyBeatsToRow fields: {missing}"


def _probe_validate_groups() -> None:
    from services.shot_grouping_llm import validate_groups

    micro = [{"duration": 3}, {"duration": 4}, {"duration": 5}]
    assert validate_groups([[0, 1, 2]], 3, micro) == [[0, 1, 2]]
    assert validate_groups([[0, 1], [2]], 3, micro) == [[0, 1], [2]]
    assert validate_groups([[0], [1, 2]], 3, micro) == [[0], [1, 2]]
    assert validate_groups([[0, 2]], 3, micro) is None
    assert validate_groups([[0, 1, 2, 3]], 3, micro) is None
    # duration overflow: 8+8 > 15
    heavy = [{"duration": 8}, {"duration": 8}]
    assert validate_groups([[0, 1]], 2, heavy) is None


def _probe_grouping() -> None:
    micro = [
        {"shotNumber": i + 1, "duration": 2, "prompt": f"细分镜{i + 1}"}
        for i in range(5)
    ]
    groups = suggest_groups(micro, target_duration=10.0)
    assert groups == [[0, 1, 2, 3, 4]], f"unexpected groups: {groups}"

    macros = build_macro_rows(micro, groups)
    assert len(macros) == 1, f"expected 1 macro row, got {len(macros)}"
    macro = macros[0]
    assert macro["duration"] == 10.0, macro["duration"]
    assert len(macro["keyframes"]) == 5, macro["keyframes"]
    assert macro.get("beatsSplitSource") == "import"
    assert macro.get("beatsSplitAt")

    missing_macro = MACRO_ROW_FIELDS - set(macro.keys())
    assert not missing_macro, f"macro row missing fields: {missing_macro}"
    _assert_keyframe_fields(macro["keyframes"])

    # 与 split_shot_beats._rule_beats 字段语义对齐（snake → camel）
    rule_row = {"duration": 10, "prompt": "测试镜头"}
    rule_beats = _rule_beats(rule_row)
    rule_keys = {"label", "time_start", "time_end", "prompt", "prompt_en", "action_note"}
    for beat in rule_beats:
        assert rule_keys <= set(beat.keys()), beat

    kf0 = macro["keyframes"][0]
    assert kf0["timeStart"] == 0.0
    assert kf0["timeEnd"] == 2.0
    assert kf0["label"]
    assert kf0["status"] == "idle"


def _probe_self_check(ep1: dict) -> None:
    sc = ep1.get("self_check") or {}
    assert sc.get("ok") is True, f"ep1 self_check failed: {sc}"

    bad_rows = copy.deepcopy(ep1["rows"])
    if len(bad_rows) >= 3:
        bad_rows[2]["shotNumber"] = 999
    bad_parsed = {**ep1, "rows": bad_rows}
    bad_sc = self_check_shot_sheet(bad_parsed)
    assert bad_sc.get("ok") is False, "scrambled shot numbers should fail self_check"


def main() -> int:
    _probe_validate_groups()
    xlsx = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    if not xlsx.is_file():
        print(f"SKIP: sample file not found: {xlsx}")
        _probe_grouping()
        print("PASS excel_import_probe (grouping only, no sample xlsx)")
        return 0

    grids = workbook_to_grids_from_path(str(xlsx))

    shot_sheets = []
    outline_sheets = []
    for name, grid in grids.items():
        kind = classify_sheet(grid)
        if kind == "shot_table":
            shot_sheets.append(name)
        elif kind == "outline":
            outline_sheets.append(name)

    assert len(shot_sheets) == 9, f"expected 9 shot sheets, got {len(shot_sheets)}: {shot_sheets}"
    assert "剧本" in outline_sheets, "missing outline sheet 剧本"

    ep1 = attach_self_check(parse_shot_sheet("第一集", grids["第一集"]))
    assert not ep1.get("error"), ep1.get("error")
    assert ep1["stats"]["shot_count"] >= 40, f"ep1 shot count low: {ep1['stats']}"
    assert ep1["stats"]["marker_count"] >= 4, f"ep1 markers low: {ep1['stats']}"
    marker_texts = [m["text"] for m in ep1["scene_markers"]]
    assert any("夜晚" in t for t in marker_texts), f"missing 夜晚 marker: {marker_texts}"
    _probe_self_check(ep1)

    ep9 = parse_shot_sheet("第九集", grids["第九集"])
    unrec = [c["header"] for c in ep9.get("unrecognized_columns") or []]
    assert any("画外音" in h for h in unrec), f"ep9 missing 画外音 column: {unrec}"

    # hash idempotency
    h1 = compute_content_hash(sheet_plaintext(grids["第二集"]))
    h2 = compute_content_hash(sheet_plaintext(grids["第二集"]))
    assert h1 == h2, "hash not stable"

    _probe_grouping()

    # 第一集建议分组 + 宏行构建 smoke
    ep1_groups = suggest_groups(ep1["rows"], target_duration=10.0)
    assert ep1_groups, "ep1 suggest_groups empty"
    ep1_macros = build_macro_rows(ep1["rows"], ep1_groups, ep1.get("segments"))
    assert len(ep1_macros) < len(ep1["rows"]), "macro count should be less than micro count"
    _assert_keyframe_fields(ep1_macros[0]["keyframes"])

    if "--llm-group" in sys.argv:
        import asyncio

        from services.shot_grouping_llm import suggest_groups_llm

        sample_rows = ep1["rows"][:12]
        llm_result = asyncio.run(suggest_groups_llm(sample_rows, ep1.get("segments")))
        assert llm_result.get("groups"), "llm grouping returned empty"
        print(
            "LLM group sample:",
            json.dumps(
                {
                    "source": llm_result.get("source"),
                    "macro_count": len(llm_result["groups"]),
                    "summary": llm_result.get("summary"),
                },
                ensure_ascii=False,
            ),
        )

    print("PASS excel_import_probe")
    print(
        json.dumps(
            {
                "shot_sheets": len(shot_sheets),
                "ep1_shots": ep1["stats"]["shot_count"],
                "ep1_markers": ep1["stats"]["marker_count"],
                "ep1_self_check_ok": ep1["self_check"]["ok"],
                "ep1_macro_shots": len(ep1_macros),
                "ep9_unrecognized": unrec,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
