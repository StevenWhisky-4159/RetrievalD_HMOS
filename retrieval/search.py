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
    analysis, results = search_method(
        args.query,
        top_k=args.top_k,
        scope=args.scope,
        path_prefix=args.path_prefix,
        code_patterns=args.code_pattern,
    )
    print(
        json.dumps(
            {
                "query_analysis": analysis.to_dict(),
                "granularity": args.granularity,
                "scope": args.scope or args.path_prefix or "all",
                "results": [result.to_dict() for result in results],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
