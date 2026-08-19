#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""匹配 query 中长度大于 2 的第一类完整词。"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from tokenizer.text_preprocessor import normalize_text

MIN_QUERY_EXACT_TERM_LENGTH = 3


@dataclass
class TrieNode:
    children: dict[str, int] = field(default_factory=dict)
    terminals: list[str] = field(default_factory=list)


class ExactQueryMatcher:
    def __init__(self, terms: Iterable[str]) -> None:
        self.nodes = [TrieNode()]
        self.term_count = 0
        for term in terms:
            normalized = normalize_text(term).casefold().strip()
            if len(normalized) < MIN_QUERY_EXACT_TERM_LENGTH:
                continue
            self._insert(normalized)
            self.term_count += 1

    def _insert(self, term: str) -> None:
        node_index = 0
        for char in term:
            target = self.nodes[node_index].children.get(char)
            if target is None:
                target = len(self.nodes)
                self.nodes[node_index].children[char] = target
                self.nodes.append(TrieNode())
            node_index = target
        if term not in self.nodes[node_index].terminals:
            self.nodes[node_index].terminals.append(term)

    def match(self, query: str) -> Counter[str]:
        normalized = normalize_text(query).casefold()
        matches: Counter[str] = Counter()
        for start in range(len(normalized)):
            node_index = 0
            position = start
            while position < len(normalized):
                target = self.nodes[node_index].children.get(normalized[position])
                if target is None:
                    break
                node_index = target
                position += 1
                for term in self.nodes[node_index].terminals:
                    matches[term] += 1
        return matches
