#!/usr/bin/env python3
"""启用 GPU 验收所需 registered_models（仅当权重文件已落盘）。

逻辑已迁至 services.registered_model_sync；本脚本供运维手动触发。
后端启动时会自动 sync_registered_models()。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.registered_model_sync import sync_registered_models


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync registered_models from model_registry")
    parser.add_argument(
        "--only",
        nargs="*",
        help="Only process these model ids (default: all known)",
    )
    args = parser.parse_args()
    only = set(args.only) if args.only else None
    changed = sync_registered_models(only=only, verbose=True)
    print(f"OK changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
