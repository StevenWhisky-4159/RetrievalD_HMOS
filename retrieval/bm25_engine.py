#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复用预计算 DF/IDF 与文档长度的 BM25 检索引擎。"""
from __future__ import annotations

import heapq
import io
import json
import pickle
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import zstandard as zstd

_HERE = Path(__file__).resolve().parent
_RETRIEVAL_ENGINE = _HERE.parent
if str(_RETRIEVAL_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ENGINE))

from retrieval.exact_query_matcher import (  # noqa: E402
    MIN_QUERY_EXACT_TERM_LENGTH,
    ExactQueryMatcher,
)
from tokenizer.text_preprocessor import TextPreprocessor  # noqa: E402

DEFAULT_INDEX_DIR = _RETRIEVAL_ENGINE / "indexing" / "data" / "index"


def load_zstd_pickle(path: Path):
    with path.open("rb") as source:
        with zstd.ZstdDecompressor().stream_reader(source) as reader:
            return pickle.load(reader)


@dataclass(frozen=True)
class SearchResult:
    rank: int
    doc_id: int
    score: float
    path: str
    titles: tuple[str, ...]
    raw_length: int
    weighted_length: int

    def to_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "doc_id": self.doc_id,
            "score": round(self.score, 6),
            "路径": self.path,
            "标题": list(self.titles),
            "raw_length": self.raw_length,
            "weighted_length": self.weighted_length,
        }


@dataclass(frozen=True)
class DocumentSearchResult:
    rank: int
    score: float
    path: str
    best_chunk_id: int
    best_chunk_titles: tuple[str, ...]
    matched_chunk_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "score": round(self.score, 6),
            "路径": self.path,
            "best_chunk_id": self.best_chunk_id,
            "best_chunk_titles": list(self.best_chunk_titles),
            "matched_chunk_count": self.matched_chunk_count,
        }


@dataclass(frozen=True)
class QueryAnalysis:
    query: str
    exact_terms: Counter[str]
    preprocessed_tokens: tuple[str, ...]
    combined_terms: Counter[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "第一类完整词": dict(sorted(self.exact_terms.items())),
            "预处理tokens": list(self.preprocessed_tokens),
            "BM25查询词频": dict(sorted(self.combined_terms.items())),
        }


class BM25Engine:
    def __init__(self, index_dir: Path = DEFAULT_INDEX_DIR) -> None:
        self.index_dir = index_dir.resolve()
        self.meta = json.loads(
            (self.index_dir / "meta.json").read_text(encoding="utf-8")
        )
        self.inverted = load_zstd_pickle(self.index_dir / "inverted.pkl.zst")
        self.term_stats = load_zstd_pickle(self.index_dir / "term_stats.pkl.zst")
        self.doc_lengths = load_zstd_pickle(self.index_dir / "doc_lengths.pkl.zst")
        exact_terms = json.loads(
            (self.index_dir / "exact_terms.json").read_text(encoding="utf-8")
        )["terms"]
        self.exact_matcher = ExactQueryMatcher(exact_terms)
        self.preprocessor = TextPreprocessor()
        self.documents = self._load_documents()

        bm25 = self.meta["bm25"]
        self.k1 = float(bm25["k1"])
        self.b = float(bm25["b"])
        self.avgdl = float(self.meta["average_raw_length"])
        self.raw_lengths = self.doc_lengths["raw"]

    def _load_documents(self) -> list[dict]:
        documents: list[dict] = []
        compressed_path = self.index_dir / "documents.jsonl.zst"
        if compressed_path.is_file():
            with compressed_path.open("rb") as compressed_source:
                with zstd.ZstdDecompressor().stream_reader(
                    compressed_source
                ) as reader:
                    with io.TextIOWrapper(reader, encoding="utf-8") as source:
                        for line in source:
                            if line.strip():
                                documents.append(json.loads(line))
        else:
            with (self.index_dir / "documents.jsonl").open(
                "r",
                encoding="utf-8",
            ) as source:
                for line in source:
                    if line.strip():
                        documents.append(json.loads(line))
        expected = int(self.meta["documents"])
        if len(documents) != expected:
            raise ValueError(
                f"documents 数量不一致: {len(documents)} != {expected}"
            )
        return documents

    def analyze_query(self, query: str) -> QueryAnalysis:
        exact_terms = self.exact_matcher.match(query)
        preprocessed_tokens = tuple(self.preprocessor.tokenize(query))
        combined = Counter(preprocessed_tokens)
        combined.update(exact_terms)
        return QueryAnalysis(
            query=query,
            exact_terms=exact_terms,
            preprocessed_tokens=preprocessed_tokens,
            combined_terms=combined,
        )

    def score_chunks(
        self,
        query: str,
    ) -> tuple[QueryAnalysis, dict[int, float]]:
        analysis = self.analyze_query(query)
        scores: defaultdict[int, float] = defaultdict(float)

        for term, query_frequency in analysis.combined_terms.items():
            posting = self.inverted.get(term)
            stats = self.term_stats.get(term)
            if posting is None or stats is None:
                continue
            _df, idf = stats
            for index in range(0, len(posting), 2):
                doc_id = posting[index]
                term_frequency = posting[index + 1]
                document_length = self.raw_lengths[doc_id]
                normalization = self.k1 * (
                    1.0
                    - self.b
                    + self.b * document_length / self.avgdl
                )
                score = (
                    idf
                    * (
                        term_frequency
                        * (self.k1 + 1.0)
                        / (term_frequency + normalization)
                    )
                    * query_frequency
                )
                scores[doc_id] += score
        return analysis, dict(scores)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        path_prefix: str | None = None,
    ) -> tuple[QueryAnalysis, list[SearchResult]]:
        analysis, scores = self.score_chunks(query)

        normalized_prefix = (
            path_prefix.replace("\\", "/").casefold()
            if path_prefix
            else ""
        )
        candidates = (
            (doc_id, score)
            for doc_id, score in scores.items()
            if not normalized_prefix
            or str(self.documents[doc_id].get("路径", ""))
            .replace("\\", "/")
            .casefold()
            .startswith(normalized_prefix)
        )
        top = heapq.nlargest(
            max(top_k, 0),
            candidates,
            key=lambda item: (item[1], -item[0]),
        )
        results: list[SearchResult] = []
        for rank, (doc_id, score) in enumerate(top, start=1):
            document = self.documents[doc_id]
            results.append(
                SearchResult(
                    rank=rank,
                    doc_id=doc_id,
                    score=score,
                    path=str(document.get("路径", "")),
                    titles=tuple(document.get("标题", [])),
                    raw_length=int(document.get("raw_length", document["length"])),
                    weighted_length=int(
                        document.get("weighted_length", document["length"])
                    ),
                )
            )
        return analysis, results

    def search_documents(
        self,
        query: str,
        *,
        top_k: int = 10,
        path_prefix: str | None = None,
    ) -> tuple[QueryAnalysis, list[DocumentSearchResult]]:
        """按路径聚合全部分片，文档分数取最高分片分数。"""
        analysis, chunk_scores = self.score_chunks(query)
        normalized_prefix = (
            path_prefix.replace("\\", "/").casefold()
            if path_prefix
            else ""
        )
        # path -> [best_score, best_chunk_id, matched_chunk_count]
        aggregated: dict[str, list[int | float]] = {}
        for chunk_id, score in chunk_scores.items():
            document = self.documents[chunk_id]
            path = str(document.get("路径", ""))
            if (
                normalized_prefix
                and not path.replace("\\", "/")
                .casefold()
                .startswith(normalized_prefix)
            ):
                continue
            current = aggregated.get(path)
            if current is None:
                aggregated[path] = [score, chunk_id, 1]
            else:
                current[2] = int(current[2]) + 1
                if score > float(current[0]) or (
                    score == float(current[0])
                    and chunk_id < int(current[1])
                ):
                    current[0] = score
                    current[1] = chunk_id

        top_documents = heapq.nlargest(
            max(top_k, 0),
            aggregated.items(),
            key=lambda item: (float(item[1][0]), item[0]),
        )
        results: list[DocumentSearchResult] = []
        for rank, (path, values) in enumerate(top_documents, start=1):
            best_score = float(values[0])
            best_chunk_id = int(values[1])
            matched_chunk_count = int(values[2])
            best_chunk = self.documents[best_chunk_id]
            results.append(
                DocumentSearchResult(
                    rank=rank,
                    score=best_score,
                    path=path,
                    best_chunk_id=best_chunk_id,
                    best_chunk_titles=tuple(best_chunk.get("标题", [])),
                    matched_chunk_count=matched_chunk_count,
                )
            )
        return analysis, results
