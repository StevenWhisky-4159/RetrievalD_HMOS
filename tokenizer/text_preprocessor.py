#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""索引和 query 共用的中英文混合文本预处理与分词模块。"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

import jieba

# 优先匹配点分 API、C++/C#、连字符词、普通英文/数字标识符。
LATIN_OR_SPECIAL_RE = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    (
        @[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+
      | [A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+
      | [A-Za-z][A-Za-z0-9_]*(?:\+\+|\#)
      | [A-Za-z0-9][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)+
      | (?=[A-Za-z0-9_]*[A-Za-z])[A-Za-z0-9_]+
    )
    (?![A-Za-z0-9_])
    """,
    re.VERBOSE,
)
CAMEL_BOUNDARY_1_RE = re.compile(r"([a-z0-9])([A-Z])")
CAMEL_BOUNDARY_2_RE = re.compile(r"([A-Z]+)([A-Z][a-z])")
PURE_NUMBER_RE = re.compile(r"^[\d._+\-]+$")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

STOPWORDS = {
    # 中文
    "的", "了", "和", "是", "在", "与", "或", "及", "为", "对", "由", "从", "到",
    "可", "可以", "能够", "应", "应当", "需要", "需", "进行", "通过", "使用", "用于",
    "以及", "等", "其", "其中", "该", "这个", "这些", "一个", "一种", "一些", "如下",
    "例如", "比如", "如果", "则", "不", "无", "非", "未", "上", "下", "中", "后", "前",
    # 英文
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "not", "but", "if", "then", "else", "for", "of", "to",
    "in", "on", "at", "by", "with", "from", "as", "into", "onto",
    "this", "that", "these", "those", "it", "its", "they", "them",
    "you", "your", "we", "our", "us", "i", "me", "my",
    "do", "does", "did", "done", "have", "has", "had",
    "will", "would", "can", "could", "should", "shall", "may", "might",
    "use", "used", "uses", "using", "example", "examples", "note", "notes",
    # 路径/文档格式噪声
    "md", "markdown",
}


def normalize_text(text: str) -> str:
    """只做 NFKC；英文大小写在 token 输出阶段统一。"""
    return unicodedata.normalize("NFKC", text)


def _is_punctuation_or_symbol(char: str) -> bool:
    category = unicodedata.category(char)
    return category.startswith("P") or category.startswith("S")


def _clean_token(token: str) -> str:
    normalized = unicodedata.normalize("NFKC", token).casefold().strip()
    if not normalized or normalized in STOPWORDS or PURE_NUMBER_RE.fullmatch(normalized):
        return ""
    if not CJK_RE.search(normalized) and len(normalized) < 2:
        return ""
    return normalized


def _camel_parts(value: str) -> list[str]:
    value = CAMEL_BOUNDARY_2_RE.sub(r"\1 \2", value)
    value = CAMEL_BOUNDARY_1_RE.sub(r"\1 \2", value)
    return value.split()


def expand_special_term(surface: str) -> list[str]:
    """
    保留完整特殊词，并补充点号、下划线、连字符及 CamelCase 子词。

    例如：
    @ohos.app.ability.UIAbility
      -> @ohos.app.ability.uiability, ohos, app, ability, uiability, ui
    """
    whole = _clean_token(surface)
    candidates: list[str] = [whole] if whole else []
    without_prefix = surface.lstrip("@")
    for component in re.split(r"[._\-]+", without_prefix):
        if not component:
            continue
        component_token = _clean_token(component)
        if component_token:
            candidates.append(component_token)
        for camel_part in _camel_parts(component):
            camel_token = _clean_token(camel_part)
            if camel_token:
                candidates.append(camel_token)

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


class TextPreprocessor:
    """统一处理特殊英文词、中文分词、空白、标点和停用词。"""

    def __init__(self) -> None:
        jieba.setLogLevel(jieba.logging.WARN)
        self._segmenter = jieba.Tokenizer()

    def _tokenize_non_latin(self, text: str) -> Iterator[str]:
        cleaned = "".join(
            " " if char.isspace() or _is_punctuation_or_symbol(char) else char
            for char in text
        )
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            return
        for piece in self._segmenter.cut(cleaned, cut_all=False, HMM=True):
            token = _clean_token(piece)
            if token:
                yield token

    def tokenize(self, text: str) -> Iterator[str]:
        normalized = normalize_text(text)
        cursor = 0
        for matched in LATIN_OR_SPECIAL_RE.finditer(normalized):
            if matched.start() > cursor:
                yield from self._tokenize_non_latin(normalized[cursor:matched.start()])
            yield from expand_special_term(matched.group(1))
            cursor = matched.end()
        if cursor < len(normalized):
            yield from self._tokenize_non_latin(normalized[cursor:])

    def tokenize_to_list(self, text: str) -> list[str]:
        return list(self.tokenize(text))
