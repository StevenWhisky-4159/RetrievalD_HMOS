#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单条 query 的 BM25 检索入口。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_RETRIEVAL_ENGINE = _HERE.parent
if str(_RETRIEVAL_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ENGINE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from retrieval.bm25_engine import BM25Engine, DEFAULT_INDEX_DIR  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BM25 检索")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    parser.add_argument(
        "--granularity",
        choices=("chunk", "document"),
        default="chunk",
        help="返回分片级或文档级结果",
    )
    parser.add_argument(
        "--document-score-mode",
        choices=("max", "weighted", "max_plus_sum"),
        default="max",
        help="文档级评分使用最高分、加权分或最高分加分片总分平均",
    )
    parser.add_argument(
        "--max-score-weight",
        type=float,
        default=0.5,
        help="weighted 模式下最高分片权重，平均分权重为 1 减去该值",
    )
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument(
        "--scope",
        default=None,
        help="检索板块，如 guides、basic-skills 或 all",
    )
    scope_group.add_argument(
        "--path-prefix",
        default=None,
        help="兼容入口：仅检索指定路径前缀，如 harmonyos-guides/",
    )
    parser.add_argument(
        "--code-pattern",
        action="append",
        default=[],
        help="块级代码正则表达式，可重复传入",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = BM25Engine(args.index_dir)
    search_method = (
        engine.search_documents
        if args.granularity == "document"
        else engine.search
    )
    search_kwargs = {
        "top_k": args.top_k,
        "scope": args.scope,
        "path_prefix": args.path_prefix,
        "code_patterns": args.code_pattern,
    }
    if args.granularity == "document":
        search_kwargs.update(
            {
                "document_score_mode": args.document_score_mode,
                "max_score_weight": args.max_score_weight,
            }
        )
    analysis, results = search_method(args.query, **search_kwargs)
    print(
        json.dumps(
            {
                "query_analysis": analysis.to_dict(),
                "granularity": args.granularity,
                "scope": args.scope or args.path_prefix or "all",
                "document_score_mode": (
                    args.document_score_mode
                    if args.granularity == "document"
                    else None
                ),
                "results": [result.to_dict() for result in results],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
