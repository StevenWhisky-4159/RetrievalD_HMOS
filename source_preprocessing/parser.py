#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 kit-routing.md 中的 Kit 路由表。"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

KIT_TABLE_HEADERS = ("kit", "指南", "basicskill", "api参考")
NAME_RE = re.compile(
    r"^(?P<en>.+?)\s*[（(](?P<zh>.+)[）)]\s*$",
)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$")
SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}")


@dataclass(frozen=True)
class KitRecord:
    领域: str
    中文: str
    英文: str
    对应指南: str
    basic_skill: str
    API参考: str

    def to_row(self) -> dict[str, str]:
        raw = asdict(self)
        return {
            "领域": raw["领域"],
            "中文": raw["中文"],
            "英文": raw["英文"],
            "对应指南": raw["对应指南"],
            "basic skill": raw["basic_skill"],
            "API参考": raw["API参考"],
        }


def split_kit_name(raw: str) -> tuple[str, str]:
    """将「English（中文）」拆成 (英文, 中文)。无法拆分时英文取原文、中文为空。"""
    text = raw.strip()
    matched = NAME_RE.match(text)
    if not matched:
        return text, ""
    return matched.group("en").strip(), matched.group("zh").strip()


def normalize_name(name: str) -> str:
    """统一全角括号、空白和大小写，便于跨库匹配。"""
    return (
        name.strip()
        .replace("（", "(")
        .replace("）", ")")
        .replace("／", "/")
        .replace("\\", "/")
        .rstrip("/")
        .lower()
        .replace(" ", "")
    )


def parse_folder_name(name: str) -> tuple[str, str]:
    """从文件夹名拆出 (英文, 中文)。无括号时按是否含汉字归类。"""
    text = name.strip()
    if not text:
        return "", ""
    matched = NAME_RE.match(text)
    if matched:
        return matched.group("en").strip(), matched.group("zh").strip()
    if CJK_RE.search(text):
        return "", text
    return text, ""


def _strip_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def split_markdown_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [_strip_cell(part) for part in text.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(SEPARATOR_RE.match(cell or "-") is not None for cell in cells)


def _normalize_header(cells: list[str]) -> list[str]:
    return [cell.replace(" ", "").lower() for cell in cells]


def _is_kit_header(cells: list[str]) -> bool:
    normalized = _normalize_header(cells)
    if len(normalized) < 4:
        return False
    return all(expected in normalized for expected in KIT_TABLE_HEADERS)


def parse_kit_routing(markdown: str) -> list[KitRecord]:
    """从 kit-routing.md 正文解析 Kit 记录，跳过「非 Kit 类 API 参考」。"""
    records: list[KitRecord] = []
    domain = ""
    in_kit_table = False
    seen: set[tuple[str, str]] = set()

    for raw_line in markdown.splitlines():
        heading = HEADING_RE.match(raw_line)
        if heading:
            title = heading.group(1).strip()
            in_kit_table = False
            if title.startswith("非 Kit"):
                domain = ""
                continue
            if title not in {"目录"}:
                domain = title
            continue

        if not raw_line.strip().startswith("|"):
            in_kit_table = False
            continue

        cells = split_markdown_row(raw_line)
        if _is_kit_header(cells):
            in_kit_table = True
            continue
        if not in_kit_table or _is_separator_row(cells) or len(cells) < 4:
            continue

        english, chinese = split_kit_name(cells[0])
        if not english:
            continue
        key = (english, chinese)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            KitRecord(
                领域=domain,
                中文=chinese,
                英文=english,
                对应指南=cells[1],
                basic_skill=cells[2],
                API参考=cells[3],
            )
        )

    return records


def parse_kit_routing_file(path: Path) -> list[KitRecord]:
    markdown = path.read_text(encoding="utf-8")
    records = parse_kit_routing(markdown)
    if not records:
        raise ValueError(f"未能从 {path} 解析出任何 Kit 记录")
    return records


def iter_rows(records: Iterable[KitRecord]) -> list[dict[str, str]]:
    return [record.to_row() for record in records]
