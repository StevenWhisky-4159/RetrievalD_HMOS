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
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import zstandard as zstd

_HERE = Path(__file__).resolve().parent
_RETRIEVAL_ENGINE = _HERE.parent
if str(_RETRIEVAL_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RETRIEVAL_ENGINE))

from retrieval.exact_query_matcher import (  # noqa: E402
    ExactQueryMatcher,
)
from retrieval.mappers import (  # noqa: E402
    BoardMapper,
    ChunkDocumentMapper,
    CodePatternMatcher,
    normalize_path,
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
    max_chunk_score: float
    average_chunk_score: float
    path: str
    best_chunk_id: int
    best_chunk_titles: tuple[str, ...]
    matched_chunk_count: int
    document_chunk_count: int
    score_mode: str
    max_score_weight: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "rank": self.rank,
            "score": round(self.score, 6),
            "max_chunk_score": round(self.max_chunk_score, 6),
            "average_chunk_score": round(self.average_chunk_score, 6),
            "路径": self.path,
            "best_chunk_id": self.best_chunk_id,
            "best_chunk_titles": list(self.best_chunk_titles),
            "matched_chunk_count": self.matched_chunk_count,
            "document_chunk_count": self.document_chunk_count,
            "score_mode": self.score_mode,
            "max_score_weight": self.max_score_weight,
        }


@dataclass(frozen=True)
class QueryAnalysis:
    query: str
    exact_terms: Counter[str]
    preprocessed_tokens: tuple[str, ...]
    combined_terms: Counter[str]
    code_patterns: tuple[str, ...] = ()
    code_pattern_matched_chunks: int = 0
    code_pattern_tf_increments: int = 0
    code_pattern_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "第一类完整词": dict(sorted(self.exact_terms.items())),
            "预处理tokens": list(self.preprocessed_tokens),
            "BM25查询词频": dict(sorted(self.combined_terms.items())),
            "代码patterns": list(self.code_patterns),
            "代码pattern命中分片数": self.code_pattern_matched_chunks,
            "代码pattern词频增量": self.code_pattern_tf_increments,
            "代码pattern中文terms": list(self.code_pattern_terms),
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
        (
            self.board_mapper,
            self.chunk_document_mapper,
            self.code_pattern_matcher,
        ) = self._load_mappers()

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

    def _load_mappers(
        self,
    ) -> tuple[BoardMapper, ChunkDocumentMapper, CodePatternMatcher]:
        mappings_path = self.index_dir / "chunk_mappings.pkl.zst"
        if mappings_path.is_file():
            mappings = load_zstd_pickle(mappings_path)
        else:
            mappings = self._derive_mappings()

        chunk_to_document = mappings["chunk_to_document"]
        if len(chunk_to_document) != len(self.documents):
            raise ValueError(
                "chunk_to_document 数量不一致: "
                f"{len(chunk_to_document)} != {len(self.documents)}"
            )
        board_mapper = BoardMapper(
            mappings["board_chunks"],
            [str(document.get("路径", "")) for document in self.documents],
        )
        chunk_document_mapper = ChunkDocumentMapper(
            chunk_to_document,
            mappings["document_paths"],
            mappings["document_to_chunks"],
        )
        code_pattern_matcher = CodePatternMatcher(
            mappings.get("code_units", mappings.get("code_blocks", {}))
        )
        return board_mapper, chunk_document_mapper, code_pattern_matcher

    def _derive_mappings(self) -> dict[str, object]:
        board_chunks: defaultdict[str, list[int]] = defaultdict(list)
        chunk_to_document: list[int] = []
        document_id_by_path: dict[str, int] = {}
        document_paths: list[str] = []
        document_to_chunks: list[list[int]] = []
        for chunk_id, document in enumerate(self.documents):
            path = str(document.get("路径", ""))
            normalized = normalize_path(path)
            board, _separator, _remainder = normalized.partition("/")
            if board:
                board_chunks[board].append(chunk_id)
            document_id = document_id_by_path.get(path)
            if document_id is None:
                document_id = len(document_paths)
                document_id_by_path[path] = document_id
                document_paths.append(path)
                document_to_chunks.append([])
            chunk_to_document.append(document_id)
            document_to_chunks[document_id].append(chunk_id)
        return {
            "board_chunks": dict(board_chunks),
            "chunk_to_document": chunk_to_document,
            "document_paths": document_paths,
            "document_to_chunks": document_to_chunks,
        }

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
        *,
        candidate_chunk_ids: frozenset[int] | None = None,
        code_patterns: Sequence[str] = (),
    ) -> tuple[QueryAnalysis, dict[int, float]]:
        analysis = self.analyze_query(query)
        code_matches = self.code_pattern_matcher.match(
            code_patterns,
            candidate_chunk_ids=candidate_chunk_ids,
        )
        analysis = replace(
            analysis,
            code_patterns=tuple(code_patterns),
            code_pattern_matched_chunks=len(code_matches),
            code_pattern_tf_increments=sum(
                increment for _term, increment in code_matches.values()
            ),
            code_pattern_terms=tuple(
                sorted({term for term, _increment in code_matches.values()})
            ),
        )
        scores: defaultdict[int, float] = defaultdict(float)

        for term, query_frequency in analysis.combined_terms.items():
            posting = self.inverted.get(term)
            stats = self.term_stats.get(term)
            if posting is None or stats is None:
                continue
            _df, idf = stats
            for index in range(0, len(posting), 2):
                doc_id = posting[index]
                if (
                    candidate_chunk_ids is not None
                    and doc_id not in candidate_chunk_ids
                ):
                    continue
                term_frequency = posting[index + 1]
                code_match = code_matches.get(doc_id)
                if code_match is not None and code_match[0] == term:
                    term_frequency += code_match[1]
                scores[doc_id] += self._bm25_term_score(
                    doc_id,
                    term_frequency,
                    float(idf),
                    query_frequency,
                )

        query_terms = analysis.combined_terms.keys()
        for doc_id, (chinese_term, term_frequency) in code_matches.items():
            if chinese_term in query_terms:
                continue
            stats = self.term_stats.get(chinese_term)
            if stats is None:
                continue
            _df, idf = stats
            scores[doc_id] += self._bm25_term_score(
                doc_id,
                term_frequency,
                float(idf),
                1,
            )
        return analysis, dict(scores)

    def _bm25_term_score(
        self,
        doc_id: int,
        term_frequency: int,
        idf: float,
        query_frequency: int,
    ) -> float:
        document_length = self.raw_lengths[doc_id]
        normalization = self.k1 * (
            1.0
            - self.b
            + self.b * document_length / self.avgdl
        )
        return (
            idf
            * (
                term_frequency
                * (self.k1 + 1.0)
                / (term_frequency + normalization)
            )
            * query_frequency
        )

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        scope: str | None = None,
        path_prefix: str | None = None,
        code_patterns: Sequence[str] = (),
    ) -> tuple[QueryAnalysis, list[SearchResult]]:
        candidate_chunk_ids = self.board_mapper.resolve(
            scope=scope,
            path_prefix=path_prefix,
        )
        analysis, scores = self.score_chunks(
            query,
            candidate_chunk_ids=candidate_chunk_ids,
            code_patterns=code_patterns,
        )
        top = heapq.nlargest(
            max(top_k, 0),
            scores.items(),
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
        scope: str | None = None,
        path_prefix: str | None = None,
        code_patterns: Sequence[str] = (),
        document_score_mode: str = "max",
        max_score_weight: float = 0.5,
    ) -> tuple[QueryAnalysis, list[DocumentSearchResult]]:
        """通过分片映射聚合文档，支持最高分片或最高分与平均分加权。"""
        if document_score_mode not in {"max", "weighted", "max_plus_sum"}:
            raise ValueError(
                f"不支持的 document_score_mode: {document_score_mode}"
            )
        if not 0.0 <= max_score_weight <= 1.0:
            raise ValueError("max_score_weight 必须在 0 到 1 之间")
        candidate_chunk_ids = self.board_mapper.resolve(
            scope=scope,
            path_prefix=path_prefix,
        )
        analysis, chunk_scores = self.score_chunks(
            query,
            candidate_chunk_ids=candidate_chunk_ids,
            code_patterns=code_patterns,
        )
        # document_id -> [best_score, best_chunk_id, matched_count, score_sum]
        aggregated: dict[int, list[int | float]] = {}
        for chunk_id, score in chunk_scores.items():
            document_id = self.chunk_document_mapper.document_id_for_chunk(chunk_id)
            current = aggregated.get(document_id)
            if current is None:
                aggregated[document_id] = [score, chunk_id, 1, score]
            else:
                current[2] = int(current[2]) + 1
                current[3] = float(current[3]) + score
                if score > float(current[0]) or (
                    score == float(current[0])
                    and chunk_id < int(current[1])
                ):
                    current[0] = score
                    current[1] = chunk_id

        scored_documents: list[
            tuple[int, float, float, int, list[int | float]]
        ] = []
        for document_id, values in aggregated.items():
            document_chunk_count = len(
                self.chunk_document_mapper.chunks_for_document(document_id)
            )
            average_score = (
                float(values[3]) / document_chunk_count
                if document_chunk_count
                else 0.0
            )
            max_score = float(values[0])
            if document_score_mode == "max":
                final_score = max_score
            elif document_score_mode == "weighted":
                final_score = (
                    max_score_weight * max_score
                    + (1.0 - max_score_weight) * average_score
                )
            else:
                final_score = (
                    max_score + float(values[3])
                ) / (document_chunk_count + 1)
            scored_documents.append(
                (
                    document_id,
                    final_score,
                    average_score,
                    document_chunk_count,
                    values,
                )
            )

        top_documents = heapq.nlargest(
            max(top_k, 0),
            scored_documents,
            key=lambda item: (
                item[1],
                self.chunk_document_mapper.path_for_document(item[0]),
            ),
        )
        results: list[DocumentSearchResult] = []
        for rank, (
            document_id,
            final_score,
            average_score,
            document_chunk_count,
            values,
        ) in enumerate(top_documents, start=1):
            best_score = float(values[0])
            best_chunk_id = int(values[1])
            matched_chunk_count = int(values[2])
            best_chunk = self.documents[best_chunk_id]
            path = self.chunk_document_mapper.path_for_document(document_id)
            results.append(
                DocumentSearchResult(
                    rank=rank,
                    score=final_score,
                    max_chunk_score=best_score,
                    average_chunk_score=average_score,
                    path=path,
                    best_chunk_id=best_chunk_id,
                    best_chunk_titles=tuple(best_chunk.get("标题", [])),
                    matched_chunk_count=matched_chunk_count,
                    document_chunk_count=document_chunk_count,
                    score_mode=document_score_mode,
                    max_score_weight=(
                        max_score_weight
                        if document_score_mode == "weighted"
                        else (
                            1.0
                            if document_score_mode == "max"
                            else None
                        )
                    ),
                )
            )
        return analysis, results
