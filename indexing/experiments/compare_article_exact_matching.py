#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""比较分片级与文章级第一类词正文匹配，不修改生产索引。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from itertools import groupby
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_INDEXING = _HERE.parent
_RETRIEVAL_ENGINE = _INDEXING.parent
if str(_RETRIEVAL_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ENGINE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from indexing.build_inverted_index import (  # noqa: E402
    exact_term_frequencies,
    iter_jsonl,
)
from indexing.exact_term_matcher import (  # noqa: E402
    MIN_BODY_EXACT_TERM_LENGTH,
    count_local_exact_terms,
)

DEFAULT_CORPUS = _INDEXING / "data" / "markdown_paragraph_corpus.jsonl"
DEFAULT_OUTPUT = (
    _INDEXING
    / "data"
    / "experiments"
    / "article_exact_matching_report.json"
)


def compare(corpus_path: Path, *, sample_limit: int = 20) -> dict[str, object]:
    started = time.time()
    article_count = 0
    chunk_count = 0
    chunk_scope_matches = 0
    article_scope_matches = 0
    chunks_with_increase = 0
    article_term_total = 0
    chunk_term_total = 0
    max_article_terms = 0
    samples: list[dict[str, object]] = []

    rows = iter_jsonl(corpus_path)
    for path, grouped_rows in groupby(rows, key=lambda row: row.get("路径", "")):
        article_rows = list(grouped_rows)
        article_count += 1
        article_terms: set[str] = set()
        chunk_terms_list: list[set[str]] = []
        for row in article_rows:
            chunk_terms = set(exact_term_frequencies(row))
            chunk_terms_list.append(chunk_terms)
            article_terms.update(chunk_terms)

        article_term_total += len(article_terms)
        max_article_terms = max(max_article_terms, len(article_terms))

        for row, chunk_terms in zip(article_rows, chunk_terms_list):
            chunk_count += 1
            chunk_term_total += len(chunk_terms)
            body = row.get("原文", "")
            if not isinstance(body, str) or not body:
                continue

            chunk_frequencies = count_local_exact_terms(body, chunk_terms)
            article_frequencies = count_local_exact_terms(body, article_terms)
            chunk_matches = sum(chunk_frequencies.values())
            article_matches = sum(article_frequencies.values())
            chunk_scope_matches += chunk_matches
            article_scope_matches += article_matches

            if article_matches > chunk_matches:
                chunks_with_increase += 1
                added = article_frequencies - chunk_frequencies
                if len(samples) < sample_limit:
                    samples.append(
                        {
                            "路径": path,
                            "标题": row.get("标题", []),
                            "分片级命中": chunk_matches,
                            "文章级命中": article_matches,
                            "新增命中": dict(
                                sorted(
                                    added.items(),
                                    key=lambda item: (-item[1], item[0]),
                                )
                            ),
                        }
                    )

        if article_count % 1000 == 0:
            print(
                f"[info] 文章 {article_count}，分片 {chunk_count}，"
                f"新增命中 {article_scope_matches - chunk_scope_matches}",
                flush=True,
            )

    delta = article_scope_matches - chunk_scope_matches
    return {
        "配置": {
            "正文第一类词最小长度": MIN_BODY_EXACT_TERM_LENGTH,
            "生产索引已修改": False,
        },
        "文章数": article_count,
        "分片数": chunk_count,
        "分片级命中总数": chunk_scope_matches,
        "文章级命中总数": article_scope_matches,
        "新增命中总数": delta,
        "新增比例": (
            round(delta / chunk_scope_matches, 6)
            if chunk_scope_matches
            else 0
        ),
        "命中增加的分片数": chunks_with_increase,
        "命中增加的分片比例": (
            round(chunks_with_increase / chunk_count, 6)
            if chunk_count
            else 0
        ),
        "平均每分片第一类词数": (
            round(chunk_term_total / chunk_count, 4)
            if chunk_count
            else 0
        ),
        "平均每文章第一类词数": (
            round(article_term_total / article_count, 4)
            if article_count
            else 0
        ),
        "单文章最大第一类词数": max_article_terms,
        "差异样例": samples,
        "耗时秒": round(time.time() - started, 2),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比较分片级与文章级第一类词匹配")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-limit", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    corpus_path = args.corpus.resolve()
    output_path = args.output.resolve()
    if not corpus_path.is_file():
        print(f"[error] 语料不存在: {corpus_path}", file=sys.stderr)
        return 1
    report = compare(corpus_path, sample_limit=max(args.sample_limit, 0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[ok] 报告: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
