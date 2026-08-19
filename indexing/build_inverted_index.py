#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基于分片词频和第一类精确 term 构建压缩倒排索引。"""
from __future__ import annotations

import argparse
import array
import itertools
import json
import math
import pickle
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

import zstandard as zstd

_HERE = Path(__file__).resolve().parent
_RETRIEVAL_ENGINE = _HERE.parent
if str(_RETRIEVAL_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ENGINE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from source_preprocessing.parser import parse_folder_name  # noqa: E402
from indexing.exact_term_matcher import (  # noqa: E402
    MIN_BODY_EXACT_TERM_LENGTH,
    count_local_exact_terms,
)
from tokenizer.text_preprocessor import normalize_text  # noqa: E402

DEFAULT_DATA_DIR = _HERE / "data"
DEFAULT_CORPUS = DEFAULT_DATA_DIR / "markdown_paragraph_corpus.jsonl"
DEFAULT_TF = DEFAULT_DATA_DIR / "chunk_term_frequencies.jsonl"
DEFAULT_OUTPUT_DIR = DEFAULT_DATA_DIR / "index"

CHILD_CHINESE_WEIGHT = 4
CHILD_ENGLISH_WEIGHT = 4
TITLE_WEIGHT = 3
ANCESTOR_DIRECTORY_WEIGHT = 2
BM25_K1 = 1.5
BM25_B = 0.75
SPACE_RE = re.compile(r"\s+")


def normalize_exact_term(value: str) -> str:
    return SPACE_RE.sub(" ", normalize_text(value).casefold()).strip()


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path} 第 {line_number} 行 JSON 错误: {error}") from error


def _add_term(counter: Counter[str], value: object, weight: int) -> None:
    if isinstance(value, str) and value.strip():
        normalized = normalize_exact_term(value)
        if normalized:
            counter[normalized] += weight


def ancestor_directory_terms(path: str) -> list[str]:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    directory_parts = parts[:-1]
    if len(directory_parts) < 2:
        return []
    result: list[str] = []
    for ancestor_name in directory_parts[:-1]:
        english, chinese = parse_folder_name(ancestor_name)
        if chinese:
            result.append(chinese)
        if english:
            result.append(english)
        if not english and not chinese:
            result.append(ancestor_name)
    return result


def exact_term_frequencies(row: dict) -> Counter[str]:
    frequencies: Counter[str] = Counter()
    _add_term(frequencies, row.get("所属子目录中文"), CHILD_CHINESE_WEIGHT)
    _add_term(frequencies, row.get("所属子目录英文"), CHILD_ENGLISH_WEIGHT)

    headings = row.get("标题", [])
    if isinstance(headings, str):
        headings = [headings]
    if isinstance(headings, list):
        for heading in headings:
            _add_term(frequencies, heading, TITLE_WEIGHT)

    path = row.get("路径", "")
    if isinstance(path, str):
        for ancestor in ancestor_directory_terms(path):
            _add_term(frequencies, ancestor, ANCESTOR_DIRECTORY_WEIGHT)
    return frequencies


def build_index(
    corpus_path: Path,
    term_frequency_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    documents_path = output_dir / "documents.jsonl"
    compressed_documents_path = output_dir / "documents.jsonl.zst"
    inverted_path = output_dir / "inverted.pkl.zst"
    doc_lengths_path = output_dir / "doc_lengths.pkl.zst"
    term_stats_path = output_dir / "term_stats.pkl.zst"
    exact_terms_path = output_dir / "exact_terms.json"
    metadata_path = output_dir / "meta.json"
    documents_tmp = documents_path.with_suffix(".jsonl.tmp")
    compressed_documents_tmp = compressed_documents_path.with_suffix(".zst.tmp")
    inverted_tmp = inverted_path.with_suffix(".zst.tmp")
    doc_lengths_tmp = doc_lengths_path.with_suffix(".zst.tmp")
    term_stats_tmp = term_stats_path.with_suffix(".zst.tmp")
    exact_terms_tmp = exact_terms_path.with_suffix(".json.tmp")
    metadata_tmp = metadata_path.with_suffix(".json.tmp")

    print("[stage 1/1] 构建倒排索引", flush=True)
    postings: dict[str, array.array] = defaultdict(lambda: array.array("I"))
    raw_lengths = array.array("I")
    weighted_lengths = array.array("I")
    exact_terms: set[str] = set()
    document_count = total_raw_length = total_weighted_length = total_postings = 0
    total_body_exact_matches = 0
    started = time.time()

    with documents_tmp.open("w", encoding="utf-8", newline="\n") as documents:
        for corpus_row, tf_row in itertools.zip_longest(
            iter_jsonl(corpus_path),
            iter_jsonl(term_frequency_path),
        ):
            if corpus_row is None or tf_row is None:
                raise ValueError("语料与词频表的分片数量不一致")
            doc_id = document_count
            if tf_row.get("chunk_id") != doc_id:
                raise ValueError(f"词频表 chunk_id 不连续: {tf_row.get('chunk_id')}")
            if corpus_row.get("路径") != tf_row.get("路径"):
                raise ValueError(f"分片 {doc_id} 的路径不一致")

            base = tf_row.get("term_frequencies")
            if not isinstance(base, dict):
                raise ValueError(f"分片 {doc_id} 缺少 term_frequencies")
            frequencies: Counter[str] = Counter(
                {
                    str(term): int(frequency)
                    for term, frequency in base.items()
                    if int(frequency) > 0
                }
            )
            exact = exact_term_frequencies(corpus_row)
            exact_terms.update(exact)
            body = corpus_row.get("原文", "")
            body_exact = (
                count_local_exact_terms(body, exact)
                if isinstance(body, str) and body
                else Counter()
            )
            frequencies.update(body_exact)
            total_body_exact_matches += sum(body_exact.values())
            raw_length = sum(frequencies.values())
            frequencies.update(exact)
            weighted_length = sum(frequencies.values())

            for term, frequency in frequencies.items():
                postings[term].append(doc_id)
                postings[term].append(frequency)
                total_postings += 1

            documents.write(
                json.dumps(
                    {
                        "id": doc_id,
                        "路径": corpus_row.get("路径", ""),
                        "标题": corpus_row.get("标题", []),
                        "length": raw_length,
                        "raw_length": raw_length,
                        "weighted_length": weighted_length,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
            raw_lengths.append(raw_length)
            weighted_lengths.append(weighted_length)
            document_count += 1
            total_raw_length += raw_length
            total_weighted_length += weighted_length
            if document_count % 10000 == 0:
                print(
                    f"[info] 已索引 {document_count} 条，terms {len(postings)}，"
                    f"postings {total_postings}",
                    flush=True,
                )

    with inverted_tmp.open("wb") as raw_output:
        with zstd.ZstdCompressor(level=6).stream_writer(raw_output) as compressed:
            pickle.dump(dict(postings), compressed, protocol=pickle.HIGHEST_PROTOCOL)

    with documents_tmp.open("rb") as source:
        with compressed_documents_tmp.open("wb") as raw_output:
            with zstd.ZstdCompressor(level=6).stream_writer(raw_output) as compressed:
                shutil.copyfileobj(source, compressed)

    doc_lengths = {
        "raw": raw_lengths,
        "weighted": weighted_lengths,
    }
    with doc_lengths_tmp.open("wb") as raw_output:
        with zstd.ZstdCompressor(level=6).stream_writer(raw_output) as compressed:
            pickle.dump(doc_lengths, compressed, protocol=pickle.HIGHEST_PROTOCOL)

    # IDF 与 term 来源无关，仅由 N 和 DF 决定。
    term_stats = {
        term: (
            len(posting) // 2,
            math.log(
                1.0
                + (
                    document_count - (len(posting) // 2) + 0.5
                )
                / ((len(posting) // 2) + 0.5)
            ),
        )
        for term, posting in postings.items()
    }
    with term_stats_tmp.open("wb") as raw_output:
        with zstd.ZstdCompressor(level=6).stream_writer(raw_output) as compressed:
            pickle.dump(term_stats, compressed, protocol=pickle.HIGHEST_PROTOCOL)
    with exact_terms_tmp.open("w", encoding="utf-8") as output:
        json.dump({"terms": sorted(exact_terms)}, output, ensure_ascii=False, indent=2)
        output.write("\n")

    elapsed = time.time() - started
    metadata = {
        "documents": document_count,
        "terms": len(postings),
        "postings": total_postings,
        "body_exact_term_matches": total_body_exact_matches,
        "body_exact_matching_scope": "current_chunk_exact_terms_only",
        "body_exact_min_term_length": MIN_BODY_EXACT_TERM_LENGTH,
        "average_raw_length": (
            round(total_raw_length / document_count, 4)
            if document_count
            else 0
        ),
        "average_weighted_length": (
            round(total_weighted_length / document_count, 4)
            if document_count
            else 0
        ),
        "bm25": {
            "k1": BM25_K1,
            "b": BM25_B,
            "document_length": "raw_length",
            "term_frequency": "weighted_tf",
            "idf_formula": "log(1 + (N - df + 0.5) / (df + 0.5))",
        },
        "reusable_data": {
            "documents": "documents.jsonl.zst",
            "doc_lengths": "doc_lengths.pkl.zst",
            "term_stats": "term_stats.pkl.zst",
            "term_stats_value": "(df, idf)",
        },
        "posting_format": "array('I') interleaved [doc_id, weighted_tf, ...]",
        "weights": {
            "child_directory_chinese": CHILD_CHINESE_WEIGHT,
            "child_directory_english": CHILD_ENGLISH_WEIGHT,
            "markdown_heading": TITLE_WEIGHT,
            "ancestor_directory_each_level": ANCESTOR_DIRECTORY_WEIGHT,
            "body_exact_term_occurrence": 1,
            "preprocessed_token": 1,
        },
        "elapsed_seconds": round(elapsed, 2),
    }
    with metadata_tmp.open("w", encoding="utf-8") as output:
        json.dump(metadata, output, ensure_ascii=False, indent=2)
        output.write("\n")

    documents_tmp.replace(documents_path)
    compressed_documents_tmp.replace(compressed_documents_path)
    inverted_tmp.replace(inverted_path)
    doc_lengths_tmp.replace(doc_lengths_path)
    term_stats_tmp.replace(term_stats_path)
    exact_terms_tmp.replace(exact_terms_path)
    metadata_tmp.replace(metadata_path)
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建加权压缩倒排索引")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--term-frequencies", type=Path, default=DEFAULT_TF)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    corpus_path = args.corpus.resolve()
    term_frequency_path = args.term_frequencies.resolve()
    output_dir = args.output_dir.resolve()
    for path in (corpus_path, term_frequency_path):
        if not path.is_file():
            print(f"[error] 文件不存在: {path}", file=sys.stderr)
            return 1
    metadata = build_index(corpus_path, term_frequency_path, output_dir)
    print("[ok] 倒排索引构建完成")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(f"[ok] 输出目录: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
