#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据 kit-routing.md 生成 Kit 路由 Excel。

列：领域、中文、英文、对应指南、basic skill、API参考。

用法（在仓库根目录 hos_skills/ 下）:
    python scripts/retrieval_engine/source_preprocessing/build_kit_excel.py
    python scripts/retrieval_engine/source_preprocessing/build_kit_excel.py ^
        --input harmonyos-sdk-coding-basic-skill/references/kit-routing.md ^
        --output scripts/retrieval_engine/source_preprocessing/data/kit_routing.xlsx
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from .excel_writer import write_kit_excel  # type: ignore[import-not-found]
    from .parser import parse_kit_routing_file  # type: ignore[import-not-found]
except ImportError:
    from excel_writer import write_kit_excel  # noqa: E402
    from parser import parse_kit_routing_file  # noqa: E402

_REPO = _HERE.parents[2]
DEFAULT_INPUT = _REPO / "harmonyos-sdk-coding-basic-skill" / "references" / "kit-routing.md"
DEFAULT_OUTPUT = _HERE / "data" / "kit_routing.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 kit-routing.md 生成 Kit 路由 Excel")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="kit-routing.md 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 xlsx 路径")
    return parser.parse_args()


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (_REPO / path)


def main() -> int:
    args = parse_args()
    input_path = _resolve_path(args.input)
    output_path = _resolve_path(args.output)

    if not input_path.is_file():
        print(f"[error] 找不到输入文件: {input_path}", file=sys.stderr)
        return 1

    records = parse_kit_routing_file(input_path)
    write_kit_excel(records, output_path)

    domain_counts = Counter(record.领域 for record in records)
    unnamed = sum(1 for record in records if not record.中文)
    print(f"[ok] 解析 Kit 数: {len(records)}")
    for domain, count in domain_counts.items():
        print(f"     {domain}: {count}")
    if unnamed:
        print(f"[warn] {unnamed} 条未能拆出中文名", file=sys.stderr)
    print(f"[ok] Excel: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
