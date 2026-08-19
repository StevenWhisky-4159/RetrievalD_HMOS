#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计正文中属于当前分片的第一类完整 term。"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from tokenizer.text_preprocessor import normalize_text

MIN_BODY_EXACT_TERM_LENGTH = 2


def count_local_exact_terms(text: str, terms: Iterable[str]) -> Counter[str]:
    """仅统计当前分片中长度至少为 2 的第一类词，允许重叠。"""
    normalized_text = normalize_text(text).casefold()
    frequencies: Counter[str] = Counter()
    for term in terms:
        normalized_term = normalize_text(term).casefold().strip()
        if len(normalized_term) < MIN_BODY_EXACT_TERM_LENGTH:
            continue
        start = 0
        while True:
            position = normalized_text.find(normalized_term, start)
            if position < 0:
                break
            frequencies[normalized_term] += 1
            start = position + 1
    return frequencies
