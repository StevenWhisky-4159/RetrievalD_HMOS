#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 Markdown 文档路径聚合最高分片后进行 guides-only 评测。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_RETRIEVAL_ENGINE = _HERE.parent
if str(_RETRIEVAL_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ENGINE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from evaluate.evaluate_random import normalize_path  # noqa: E402
from retrieval.bm25_engine import BM25Engine, DEFAULT_INDEX_DIR  # noqa: E402

DEFAULT_DATASET = _HERE / "dataset" / "dataset.xlsx"
DEFAULT_OUTPUT = _HERE / "data" / "document_random_20_results.json"
DEFAULT_PATH_PREFIX = "harmonyos-guides/"


def gold_rank(gold_path: str, results) -> int:
    normalized_gold = normalize_path(gold_path)
    for result in results:
        if normalize_path(result.path) == normalized_gold:
            return result.rank
    return 0


def evaluate(
    dataset_path: Path,
    output_path: Path,
    *,
    sample_size: int = 20,
    seed: int = 2026,
    top_k: int = 10,
    document_score_mode: str = "max",
    max_score_weight: float = 0.5,
    index_dir: Path = DEFAULT_INDEX_DIR,
) -> dict[str, object]:
    dataframe = pd.read_excel(dataset_path)
    required = {"提问", "原始路径"}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError(f"dataset 缺少列: {sorted(missing)}")
    available = dataframe[
        dataframe["提问"].notna() & dataframe["原始路径"].notna()
    ]
    sample = available.sample(
        n=min(sample_size, len(available)),
        random_state=seed,
    )

    engine = BM25Engine(index_dir)
    started = time.time()
    cases: list[dict[str, object]] = []
    ranks: list[int] = []
    for order, (row_index, row) in enumerate(sample.iterrows(), start=1):
        query = str(row["提问"]).strip()
        gold = str(row["原始路径"]).strip()
        analysis, results = engine.search_documents(
            query,
            top_k=top_k,
            path_prefix=DEFAULT_PATH_PREFIX,
            document_score_mode=document_score_mode,
            max_score_weight=max_score_weight,
        )
        rank = gold_rank(gold, results)
        ranks.append(rank)
        cases.append(
            {
                "sample_order": order,
                "dataset_row": int(row_index),
                "query": query,
                "gold_path": gold,
                "gold_rank": rank,
                "query_analysis": analysis.to_dict(),
                "results": [result.to_dict() for result in results],
            }
        )
        print(
            f"[{order}/{len(sample)}] gold_rank={rank or 'miss'} "
            f"exact={len(analysis.exact_terms)} query={query[:50]}",
            flush=True,
        )

    total = len(ranks)
    summary = {
        "dataset": str(dataset_path),
        "granularity": "document",
        "aggregation": (
            "max_chunk_score"
            if document_score_mode == "max"
            else (
                "weighted_max_and_all_chunk_average"
                if document_score_mode == "weighted"
                else "max_plus_chunk_score_sum_over_chunk_count_plus_one"
            )
        ),
        "document_score_mode": document_score_mode,
        "max_score_weight": (
            max_score_weight
            if document_score_mode == "weighted"
            else None
        ),
        "sample_size": total,
        "seed": seed,
        "top_k": top_k,
        "path_prefix": DEFAULT_PATH_PREFIX,
        "hit_at_1": sum(0 < rank <= 1 for rank in ranks) / total if total else 0,
        "hit_at_3": sum(0 < rank <= 3 for rank in ranks) / total if total else 0,
        "hit_at_5": sum(0 < rank <= 5 for rank in ranks) / total if total else 0,
        "hit_at_10": sum(0 < rank <= 10 for rank in ranks) / total if total else 0,
        "mrr": (
            sum(1.0 / rank for rank in ranks if rank > 0) / total
            if total
            else 0
        ),
        "exact_term_queries": sum(
            bool(case["query_analysis"]["第一类完整词"])
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
    parser = argparse.ArgumentParser(description="文档级 guides-only BM25 评测")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--document-score-mode",
        choices=("max", "weighted", "max_plus_sum"),
        default="max",
    )
    parser.add_argument("--max-score-weight", type=float, default=0.5)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dataset.is_file():
        print(f"[error] dataset 不存在: {args.dataset}", file=sys.stderr)
        return 1
    report = evaluate(
        args.dataset.resolve(),
        args.output.resolve(),
        sample_size=max(args.sample_size, 0),
        seed=args.seed,
        top_k=max(args.top_k, 0),
        document_score_mode=args.document_score_mode,
        max_score_weight=args.max_score_weight,
        index_dir=args.index_dir.resolve(),
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"[ok] 结果: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
