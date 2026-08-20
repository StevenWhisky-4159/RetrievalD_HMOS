#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索范围与分片到文档的预计算映射器。"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence


SCOPE_ALIASES = {
    "guide": "harmonyos-guides",
    "guides": "harmonyos-guides",
    "basic-skill": "harmonyos-sdk-basic-skill",
    "basic-skills": "harmonyos-sdk-basic-skill",
    "basicskill": "harmonyos-sdk-basic-skill",
    "basicskills": "harmonyos-sdk-basic-skill",
    "references": "harmonyos-references",
    "reference": "harmonyos-references",
    "faqs": "harmonyos-faqs",
    "faq": "harmonyos-faqs",
    "releases": "harmonyos-releases",
    "release": "harmonyos-releases",
    "best-practices": "best-practices",
}


def normalize_path(value: str) -> str:
    return value.replace("\\", "/").strip().strip("/").casefold()


def normalize_scope(value: str) -> str:
    return normalize_path(value).replace("_", "-").replace(" ", "-")


class BoardMapper:
    """将板块名或路径前缀映射为候选分片 ID。"""

    def __init__(
        self,
        board_chunks: dict[str, Iterable[int]],
        chunk_paths: Sequence[str],
    ) -> None:
        self.chunk_paths = tuple(normalize_path(path) for path in chunk_paths)
        self._boards = {
            normalize_scope(board): frozenset(int(chunk_id) for chunk_id in chunk_ids)
            for board, chunk_ids in board_chunks.items()
        }
        self._prefix_cache: dict[str, frozenset[int]] = {}

    @property
    def available_boards(self) -> tuple[str, ...]:
        return tuple(sorted(self._boards))

    def chunks_for_scope(self, scope: str | None) -> frozenset[int] | None:
        if scope is None:
            return None
        normalized = normalize_scope(scope)
        if not normalized or normalized in {"all", "full"}:
            return None
        board = SCOPE_ALIASES.get(normalized, normalized)
        try:
            return self._boards[board]
        except KeyError as error:
            available = ", ".join(self.available_boards)
            raise ValueError(f"未知检索板块 {scope!r}；可用板块: {available}") from error

    def chunks_for_prefix(self, path_prefix: str | None) -> frozenset[int] | None:
        if not path_prefix:
            return None
        prefix = normalize_path(path_prefix)
        if not prefix:
            return None
        cached = self._prefix_cache.get(prefix)
        if cached is not None:
            return cached

        root, separator, _remainder = prefix.partition("/")
        root_candidates = self._boards.get(root)
        if root_candidates is None:
            result = frozenset()
        elif not separator:
            result = root_candidates
        else:
            expected = prefix + "/"
            result = frozenset(
                chunk_id
                for chunk_id in root_candidates
                if self.chunk_paths[chunk_id] == prefix
                or self.chunk_paths[chunk_id].startswith(expected)
            )
        self._prefix_cache[prefix] = result
        return result

    def resolve(
        self,
        *,
        scope: str | None = None,
        path_prefix: str | None = None,
    ) -> frozenset[int] | None:
        if scope and path_prefix:
            raise ValueError("scope 与 path_prefix 不能同时指定")
        if scope:
            return self.chunks_for_scope(scope)
        return self.chunks_for_prefix(path_prefix)


class ChunkDocumentMapper:
    """提供分片与 Markdown 文档之间的双向映射。"""

    def __init__(
        self,
        chunk_to_document: Sequence[int],
        document_paths: Sequence[str],
        document_to_chunks: Sequence[Sequence[int]],
    ) -> None:
        self.chunk_to_document = tuple(int(value) for value in chunk_to_document)
        self.document_paths = tuple(str(value) for value in document_paths)
        self.document_to_chunks = tuple(
            tuple(int(chunk_id) for chunk_id in chunk_ids)
            for chunk_ids in document_to_chunks
        )
        if len(self.document_paths) != len(self.document_to_chunks):
            raise ValueError("文档路径与文档分片映射数量不一致")

    def document_id_for_chunk(self, chunk_id: int) -> int:
        return self.chunk_to_document[chunk_id]

    def path_for_document(self, document_id: int) -> str:
        return self.document_paths[document_id]

    def chunks_for_document(self, document_id: int) -> tuple[int, ...]:
        return self.document_to_chunks[document_id]


class CodePatternMatcher:
    """匹配分片块级/行内代码，并返回中文目录 term 的动态 TF。"""

    def __init__(
        self,
        code_units: dict[int, tuple[str, Sequence[str]]],
    ) -> None:
        self.code_units = {
            int(chunk_id): (
                str(chinese_term),
                tuple(str(code) for code in units),
            )
            for chunk_id, (chinese_term, units) in code_units.items()
        }

    def match(
        self,
        patterns: Sequence[str],
        *,
        candidate_chunk_ids: frozenset[int] | None = None,
    ) -> dict[int, tuple[str, int]]:
        compiled: list[re.Pattern[str]] = []
        for pattern in patterns:
            if not isinstance(pattern, str) or not pattern:
                raise ValueError("code pattern 必须是非空字符串")
            try:
                compiled.append(re.compile(pattern))
            except re.error as error:
                raise ValueError(f"无效 code pattern {pattern!r}: {error}") from error
        if not compiled:
            return {}

        matches: dict[int, tuple[str, int]] = {}
        for chunk_id, (chinese_term, units) in self.code_units.items():
            if (
                candidate_chunk_ids is not None
                and chunk_id not in candidate_chunk_ids
            ):
                continue
            term_frequency = sum(
                bool(pattern.search(unit))
                for pattern in compiled
                for unit in units
            )
            if term_frequency:
                matches[chunk_id] = (chinese_term, term_frequency)
        return matches
