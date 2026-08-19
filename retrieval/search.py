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
        "--path-prefix",
        default=None,
        help="仅返回指定路径前缀下的文档，如 harmonyos-guides/",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = BM25Engine(args.index_dir)
    analysis, results = engine.search(
        args.query,
        top_k=args.top_k,
        path_prefix=args.path_prefix,
    )
    print(
        json.dumps(
            {
                "query_analysis": analysis.to_dict(),
                "results": [result.to_dict() for result in results],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
