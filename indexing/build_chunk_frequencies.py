#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将每个语料分片转换为统一词频表，并汇总全局 vocab。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_RETRIEVAL_ENGINE = _HERE.parent
if str(_RETRIEVAL_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ENGINE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from tokenizer.text_preprocessor import TextPreprocessor  # noqa: E402

DEFAULT_DATA_DIR = _HERE / "data"
DEFAULT_CORPUS = DEFAULT_DATA_DIR / "markdown_paragraph_corpus.jsonl"
DEFAULT_VOCAB_OUTPUT = DEFAULT_DATA_DIR / "terms_vocab.json"
DEFAULT_TF_OUTPUT = DEFAULT_DATA_DIR / "chunk_term_frequencies.jsonl"


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"JSONL 第 {line_number} 行格式错误: {error}") from error


def compose_chunk_text(row: dict) -> str:
    """严格按路径、标题、正文的顺序使用换行符拼接。"""
    parts: list[str] = []
    path = row.get("路径")
    if isinstance(path, str) and path.strip():
        parts.append(path.strip())

    headings = row.get("标题", [])
    if isinstance(headings, str):
        headings = [headings]
    if isinstance(headings, list):
        parts.extend(
            heading.strip()
            for heading in headings
            if isinstance(heading, str) and heading.strip()
        )

    original = row.get("原文")
    if isinstance(original, str) and original.strip():
        parts.append(original.strip())
    return "\n".join(parts)


def build_chunk_frequencies(
    corpus_path: Path,
    output_path: Path,
) -> tuple[set[str], int, int]:
    preprocessor = TextPreprocessor()
    vocabulary: set[str] = set()
    records = 0
    total_tokens = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
        for chunk_id, row in enumerate(iter_jsonl(corpus_path)):
            source_chunk_id = row.get("chunk_id", chunk_id)
            if source_chunk_id != chunk_id:
                raise ValueError(
                    f"语料 chunk_id 不连续: 期望 {chunk_id}，实际 {source_chunk_id}"
                )
            records += 1
            frequencies = Counter(preprocessor.tokenize(compose_chunk_text(row)))
            vocabulary.update(frequencies)
            length = sum(frequencies.values())
            total_tokens += length
            record = {
                "chunk_id": chunk_id,
                "路径": row.get("路径", ""),
                "标题": row.get("标题", []),
                "length": length,
                "term_frequencies": dict(sorted(frequencies.items())),
            }
            output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            output.write("\n")
            if records % 10000 == 0:
                print(
                    f"[info] 已处理 {records} 条，累计 token {total_tokens}，"
                    f"唯一 term {len(vocabulary)}",
                    flush=True,
                )

    temporary_path.replace(output_path)
    return vocabulary, records, total_tokens


def write_vocab(output_path: Path, vocabulary: set[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as output:
        json.dump({"terms": sorted(vocabulary)}, output, ensure_ascii=False, indent=2)
        output.write("\n")
    temporary_path.replace(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建统一词频表与 vocab")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--vocab-output", type=Path, default=DEFAULT_VOCAB_OUTPUT)
    parser.add_argument("--tf-output", type=Path, default=DEFAULT_TF_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    corpus_path = args.corpus.resolve()
    vocab_output = args.vocab_output.resolve()
    tf_output = args.tf_output.resolve()
    if not corpus_path.is_file():
        print(f"[error] 找不到语料: {corpus_path}", file=sys.stderr)
        return 1

    started = time.time()
    vocabulary, records, total_tokens = build_chunk_frequencies(corpus_path, tf_output)
    write_vocab(vocab_output, vocabulary)
    elapsed = time.time() - started
    print(f"[ok] 分片数: {records}")
    print(f"[ok] 唯一 term: {len(vocabulary)}")
    print(f"[ok] token 总数: {total_tokens}")
    print(f"[ok] vocab: {vocab_output} ({vocab_output.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"[ok] 词频表: {tf_output} ({tf_output.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"[ok] 总耗时: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
