#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 query + code patterns Excel，批量执行检索并输出 JSON 报告。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_RETRIEVAL_ENGINE = _HERE.parent
_REPO = _RETRIEVAL_ENGINE.parents[1]
if str(_RETRIEVAL_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ENGINE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from retrieval.bm25_engine import BM25Engine, DEFAULT_INDEX_DIR  # noqa: E402

DEFAULT_DATASET = _REPO / "scripts" / "code_tests" / "query_code_example.xlsx"
DEFAULT_OUTPUT = _HERE / "data" / "query_code_example_results.json"
REQUIRED_COLUMNS = {"user_prompt", "markers"}


def parse_code_patterns(value: object, *, row_number: int) -> tuple[str, ...]:
    """解析 markers JSON 数组，并提供包含 Excel 行号的错误信息。"""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Excel 第 {row_number} 行 markers 不是有效 JSON: {error}"
            ) from error
    elif isinstance(value, Sequence):
        parsed = value
    elif pd.isna(value):
        return ()
    else:
        raise ValueError(f"Excel 第 {row_number} 行 markers 必须是 JSON 字符串数组")

    if not isinstance(parsed, list) or not all(
        isinstance(pattern, str) and pattern
        for pattern in parsed
    ):
        raise ValueError(
            f"Excel 第 {row_number} 行 markers 必须是非空字符串组成的 JSON 数组"
        )
    return tuple(parsed)


def evaluate(
    dataset_path: Path,
    output_path: Path,
    *,
    sheet_name: str = "Sheet1",
    top_k: int = 10,
    granularity: str = "document",
    document_score_mode: str = "max",
    max_score_weight: float = 0.5,
    scope: str | None = None,
    path_prefix: str | None = None,
    index_dir: Path = DEFAULT_INDEX_DIR,
) -> dict[str, object]:
    if granularity not in {"chunk", "document"}:
        raise ValueError(f"不支持的 granularity: {granularity}")
    if scope and path_prefix:
        raise ValueError("scope 与 path_prefix 不能同时指定")

    dataframe = pd.read_excel(dataset_path, sheet_name=sheet_name)
    missing = REQUIRED_COLUMNS - set(dataframe.columns)
    if missing:
        raise ValueError(f"dataset 缺少列: {sorted(missing)}")

    engine = BM25Engine(index_dir)
    search_method = (
        engine.search_documents
        if granularity == "document"
        else engine.search
    )
    started = time.time()
    cases: list[dict[str, object]] = []

    for row_index, row in dataframe.iterrows():
        excel_row = int(row_index) + 2
        prompt_value = row["user_prompt"]
        if pd.isna(prompt_value) or not str(prompt_value).strip():
            continue
        query = str(prompt_value).strip()
        code_patterns = parse_code_patterns(
            row["markers"],
            row_number=excel_row,
        )
        try:
            search_kwargs = {
                "top_k": max(top_k, 0),
                "scope": scope,
                "path_prefix": path_prefix,
                "code_patterns": code_patterns,
            }
            if granularity == "document":
                search_kwargs.update(
                    {
                        "document_score_mode": document_score_mode,
                        "max_score_weight": max_score_weight,
                    }
                )
            analysis, results = search_method(query, **search_kwargs)
        except ValueError as error:
            raise ValueError(f"Excel 第 {excel_row} 行检索失败: {error}") from error

        cases.append(
            {
                "excel_row": excel_row,
                "query": query,
                "code_patterns": list(code_patterns),
                "query_analysis": analysis.to_dict(),
                "results": [result.to_dict() for result in results],
            }
        )
        print(
            f"[{len(cases)}] row={excel_row} patterns={len(code_patterns)} "
            f"matched_chunks={analysis.code_pattern_matched_chunks} "
            f"results={len(results)}",
            flush=True,
        )

    summary = {
        "dataset": str(dataset_path),
        "sheet": sheet_name,
        "rows": len(cases),
        "top_k": max(top_k, 0),
        "granularity": granularity,
        "document_score_mode": (
            document_score_mode if granularity == "document" else None
        ),
        "max_score_weight": (
            max_score_weight
            if granularity == "document"
            and document_score_mode == "weighted"
            else None
        ),
        "scope": scope or path_prefix or "all",
        "rows_with_code_matches": sum(
            case["query_analysis"]["代码pattern命中分片数"] > 0
            for case in cases
        ),
        "total_code_matched_chunks": sum(
            case["query_analysis"]["代码pattern命中分片数"]
            for case in cases
        ),
        "total_code_tf_increments": sum(
            case["query_analysis"]["代码pattern词频增量"]
            for case in cases
        ),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    report = {"summary": summary, "cases": cases}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量评测 query + code patterns 检索")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sheet", default="Sheet1")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--granularity",
        choices=("chunk", "document"),
        default="document",
        help="检索粒度，默认按 Markdown 文档聚合",
    )
    parser.add_argument(
        "--document-score-mode",
        choices=("max", "weighted", "max_plus_sum"),
        default="max",
    )
    parser.add_argument("--max-score-weight", type=float, default=0.5)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument(
        "--scope",
        choices=("all", "basic-skill", "basic-skills", "guides"),
        default=None,
        help="检索范围，默认使用全部板块",
    )
    scope_group.add_argument("--path-prefix", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_path = args.dataset.resolve()
    if not dataset_path.is_file():
        print(f"[error] dataset 不存在: {dataset_path}", file=sys.stderr)
        return 1
    report = evaluate(
        dataset_path,
        args.output.resolve(),
        sheet_name=args.sheet,
        top_k=args.top_k,
        granularity=args.granularity,
        document_score_mode=args.document_score_mode,
        max_score_weight=args.max_score_weight,
        scope=args.scope,
        path_prefix=args.path_prefix,
        index_dir=args.index_dir.resolve(),
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"[ok] 结果: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
