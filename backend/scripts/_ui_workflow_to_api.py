#!/usr/bin/env python3
"""Convert ComfyUI UI workflow JSON to API prompt dict (minimal converter)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def ui_workflow_to_api(ui: dict) -> dict:
    nodes = {str(n["id"]): n for n in ui.get("nodes", [])}
    links = ui.get("links") or []
    link_map: dict[tuple[int, int], tuple[str, int]] = {}
    for link in links:
        if len(link) < 6:
            continue
        _lid, src_id, src_slot, dst_id, dst_slot, _typ = link[:6]
        link_map[(int(dst_id), int(dst_slot))] = (str(src_id), int(src_slot))

    api: dict = {}
    for nid, node in nodes.items():
        class_type = node.get("type")
        if not class_type or class_type in ("MarkdownNote", "Reroute", "PrimitiveNode", "PrimitiveInt", "PrimitiveFloat"):
            continue
        inputs: dict = {}
        widget_values = list(node.get("widgets_values") or [])
        input_defs = node.get("inputs") or []
        widget_i = 0
        for slot_i, inp in enumerate(input_defs):
            key = inp.get("name")
            if not key:
                continue
            link_key = (int(nid), slot_i)
            if link_key in link_map:
                inputs[key] = list(link_map[link_key])
            elif "widget" in inp and widget_i < len(widget_values):
                inputs[key] = widget_values[widget_i]
                widget_i += 1
        while widget_i < len(widget_values):
            # nodes with only widget inputs (no input defs)
            break
        if class_type in ("CLIPTextEncode", "SaveVideo", "CreateVideo") and widget_values:
            if "text" not in inputs and class_type == "CLIPTextEncode":
                inputs["text"] = widget_values[0]
            if "filename_prefix" not in inputs and class_type == "SaveVideo":
                inputs["filename_prefix"] = widget_values[0] if widget_values else "AIStudio"
        api[nid] = {"class_type": class_type, "inputs": inputs}
    return api


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: _ui_workflow_to_api.py <ui.json> <api.json>", file=sys.stderr)
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    ui = json.loads(src.read_text(encoding="utf-8"))
    api = ui_workflow_to_api(ui)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(api, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(api)} nodes -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
