#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索 query 的统一预处理入口。"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from text_preprocessor import TextPreprocessor  # noqa: E402


def preprocess_query(query: str) -> dict[str, object]:
    tokens = TextPreprocessor().tokenize_to_list(query)
    return {
        "query": query,
        "tokens": tokens,
        "term_frequencies": dict(
            sorted(Counter(tokens).items(), key=lambda item: item[0])
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用索引同款预处理器处理 query")
    parser.add_argument("query", help="待处理 query")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(preprocess_query(args.query), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
