#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描文档库实际文件夹（含主题下全部子目录），生成中英文 + 指南 / skill / API 对照 Excel。

不依赖 kit-routing.md 的目录列表，因此会收录路由表未覆盖的文件夹。

用法（在仓库根目录 hos_skills/ 下）:
    python scripts/retrieval_engine/source_preprocessing/build_folder_excel.py
    python scripts/retrieval_engine/source_preprocessing/build_folder_excel.py ^
        --output scripts/retrieval_engine/source_preprocessing/data/folder_mapping.xlsx
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
    from .excel_writer import write_table_excel  # type: ignore[import-not-found]
    from .folder_catalog import FOLDER_COLUMNS, build_folder_catalog  # type: ignore[import-not-found]
except ImportError:
    from excel_writer import write_table_excel  # noqa: E402
    from folder_catalog import FOLDER_COLUMNS, build_folder_catalog  # noqa: E402

_REPO = _HERE.parents[2]
REFERENCES = _REPO / "harmonyos-sdk-coding-basic-skill" / "references"
DEFAULT_ROUTING = REFERENCES / "kit-routing.md"
DEFAULT_OUTPUT = _HERE / "data" / "folder_mapping.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从文档库文件夹生成中英文与三库路径对照 Excel")
    parser.add_argument("--references", type=Path, default=REFERENCES, help="references 根目录")
    parser.add_argument("--routing", type=Path, default=DEFAULT_ROUTING, help="kit-routing.md，用于标记是否已收录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 xlsx 路径")
    return parser.parse_args()


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (_REPO / path)


def main() -> int:
    args = parse_args()
    references = _resolve_path(args.references)
    routing = _resolve_path(args.routing)
    output_path = _resolve_path(args.output)

    if not references.is_dir():
        print(f"[error] 找不到文档库: {references}", file=sys.stderr)
        return 1

    records = build_folder_catalog(references, routing_path=routing if routing.is_file() else None)
    try:
        write_table_excel(
            [record.to_row() for record in records],
            output_path,
            columns=FOLDER_COLUMNS,
            sheet_name="文档目录",
        )
    except PermissionError:
        from time import time
        output_path = output_path.with_name(f"{output_path.stem}_{int(time())}{output_path.suffix}")
        write_table_excel(
            [record.to_row() for record in records],
            output_path,
            columns=FOLDER_COLUMNS,
            sheet_name="文档目录",
        )
        print(f"[warn] 原 Excel 被占用，已改写为: {output_path}", file=sys.stderr)

    type_counts = Counter(record.类型 for record in records)
    depth_counts = Counter(record.层级 for record in records)
    three = sum(1 for rec in records if rec.对应指南 and rec.basic_skill and rec.API参考)
    only_guide = sum(1 for rec in records if rec.对应指南 and not rec.basic_skill and not rec.API参考)
    only_skill = sum(1 for rec in records if rec.basic_skill and not rec.对应指南 and not rec.API参考)
    only_api = sum(1 for rec in records if rec.API参考 and not rec.对应指南 and not rec.basic_skill)
    no_zh = sum(1 for rec in records if not rec.中文)
    no_en = sum(1 for rec in records if not rec.英文)
    with_titles = sum(1 for rec in records if rec.Markdown标题)
    title_count = sum(len(rec.Markdown标题.splitlines()) for rec in records if rec.Markdown标题)
    missing_topics = [rec for rec in records if rec.层级 == "0" and rec.kit路由 == "否"]

    print(f"[ok] 目录条目: {len(records)}")
    print(f"     类型: {dict(type_counts)}")
    print(f"     层级: {dict(sorted(depth_counts.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 99))}")
    print(f"     三库齐全: {three}")
    print(f"     仅指南 / 仅skill / 仅API: {only_guide} / {only_skill} / {only_api}")
    print(f"     含 Markdown 标题的目录: {with_titles}，标题总数（去重后）: {title_count}")
    if no_zh:
        print(f"[warn] {no_zh} 条没有中文名")
    if no_en:
        print(f"[warn] {no_en} 条没有英文名")
    print(f"[ok] 未进 kit-routing 的主题: {len(missing_topics)}")
    for rec in missing_topics:
        label = rec.英文 or rec.中文
        trees = "+".join(
            name
            for name, path in (
                ("指南", rec.对应指南),
                ("skill", rec.basic_skill),
                ("API", rec.API参考),
            )
            if path
        )
        print(f"     - {label}  [{rec.类型}/{rec.领域}] {trees}")
    print(f"[ok] Excel: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
