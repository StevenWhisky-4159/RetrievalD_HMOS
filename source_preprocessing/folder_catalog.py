#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描文档库实际文件夹（含主题下全部子目录），拆出中英文名，
并把指南 / basic skill / API 参考按「所属主题 + 相对路径」对齐。

覆盖 kit-routing.md 未收录的目录，例如：
- 指南顶层专题及其子目录（基础入门、NDK开发、应用测试等）
- 领域下的非 Kit 兄弟目录（媒体开发概览、密码自动填充服务、Accessory Kit 等）
- 非 Kit 类 API（C API、OpenGL、开发说明等）
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    from .parser import normalize_name, parse_folder_name, parse_kit_routing_file
except ImportError:
    from parser import normalize_name, parse_folder_name, parse_kit_routing_file

DOMAIN_TOPS = {"AI", "图形", "媒体", "应用框架", "应用服务", "系统"}
KITISH_RE = re.compile(
    r"(Kit|ArkUI|ArkTS|ArkWeb|ArkData|ArkGraphics|AR Engine)",
    re.IGNORECASE,
)
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
TRAILING_HASH_RE = re.compile(r"\s+#+\s*$")
EXCEL_CELL_LIMIT = 32_767
KNOWN_NON_KIT = {
    "ArkTS API",
    "C API",
    "Node-API",
    "EGL",
    "OpenGL",
    "OpenGL ES",
    "OpenSL ES",
    "Vulkan",
    "c++标准库",
    "libc标准库",
    "libuv",
    "zlib",
    "ICU4C",
    "HiTSS",
    "开发说明",
    "系统能力SystemCapability使用指南",
    "通用错误码",
    "附录",
}
SKIP_DIR_NAMES = {
    "scripts",
    "assets",
    "tests",
    "test",
    "node_modules",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "references",
    "images",
    "image",
    "img",
    "figures",
}


@dataclass
class FolderHit:
    tree: str  # guide / skill / api
    name: str
    english: str
    chinese: str
    relative: str
    domain: str
    topic_key: str
    topic_label: str
    rel_key: str
    depth: int
    is_kit_topic: bool
    in_routing: bool
    markdown_titles: tuple[str, ...]


@dataclass
class FolderRecord:
    领域: str
    所属主题: str
    层级: str
    类型: str
    中文: str
    英文: str
    对应指南: str
    basic_skill: str
    API参考: str
    Markdown标题: str
    kit路由: str

    def to_row(self) -> dict[str, str]:
        return {
            "领域": self.领域,
            "所属主题": self.所属主题,
            "层级": self.层级,
            "类型": self.类型,
            "中文": self.中文,
            "英文": self.英文,
            "对应指南": self.对应指南,
            "basic skill": self.basic_skill,
            "API参考": self.API参考,
            "Markdown标题": self.Markdown标题,
            "kit路由": self.kit路由,
        }


FOLDER_COLUMNS = (
    "领域",
    "所属主题",
    "层级",
    "类型",
    "中文",
    "英文",
    "对应指南",
    "basic skill",
    "API参考",
    "Markdown标题",
    "kit路由",
)


def _rel(path: Path, references: Path) -> str:
    return path.relative_to(references).as_posix()


def _topic_key(english: str, chinese: str, name: str) -> str:
    if english:
        return "en:" + normalize_name(english)
    if chinese:
        return "zh:" + normalize_name(chinese)
    return "raw:" + normalize_name(name)


def _topic_label(english: str, chinese: str, name: str) -> str:
    if english and chinese:
        return f"{english}（{chinese}）"
    return english or chinese or name


def _rel_key(rel_inside: str) -> str:
    if not rel_inside:
        return ""
    return "/".join(normalize_name(part) for part in rel_inside.replace("\\", "/").split("/") if part)


def _is_kit_name(english: str, chinese: str, name: str) -> bool:
    if name in KNOWN_NON_KIT:
        return False
    title = english or name
    if chinese and KITISH_RE.search(title):
        return True
    if re.search(r"(^|[\s_])Kit$", title) or title.endswith(" Kit"):
        return True
    return bool(title.endswith("Kit") and chinese)


def iter_subdirs(root: Path):
    for dirpath, dirnames, _files in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in SKIP_DIR_NAMES and not name.startswith(".")
        ]
        current = Path(dirpath)
        if current == root:
            continue
        yield current


def extract_markdown_titles(folder: Path) -> tuple[str, ...]:
    """提取当前文件夹直接包含的 Markdown 标题，不递归读取后代目录。"""
    titles: list[str] = []
    seen: set[str] = set()

    markdown_files = sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
        ),
        key=lambda path: path.name.lower(),
    )
    for markdown_path in markdown_files:
        try:
            content = markdown_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        fence_marker = ""
        for line in content.splitlines():
            fence = FENCE_RE.match(line)
            if fence:
                marker = fence.group(1)[0]
                if not fence_marker:
                    fence_marker = marker
                elif marker == fence_marker:
                    fence_marker = ""
                continue
            if fence_marker:
                continue

            matched = MARKDOWN_HEADING_RE.match(line)
            if not matched:
                continue
            title = TRAILING_HASH_RE.sub("", matched.group(1)).strip()
            if title and title not in seen:
                seen.add(title)
                titles.append(title)

    return tuple(titles)


def _make_hit(
    path: Path,
    *,
    tree: str,
    domain: str,
    references: Path,
    topic_key: str,
    topic_label: str,
    rel_inside: str,
    is_kit_topic: bool,
    in_routing: bool,
) -> FolderHit:
    english, chinese = parse_folder_name(path.name)
    return FolderHit(
        tree=tree,
        name=path.name,
        english=english,
        chinese=chinese,
        relative=_rel(path, references),
        domain=domain,
        topic_key=topic_key,
        topic_label=topic_label,
        rel_key=_rel_key(rel_inside),
        depth=0 if not rel_inside else len(Path(rel_inside).parts),
        is_kit_topic=is_kit_topic,
        in_routing=in_routing,
        markdown_titles=extract_markdown_titles(path),
    )


def _topic_in_routing(english: str, chinese: str, routing_keys: set[str]) -> bool:
    if english and normalize_name(english) in routing_keys:
        return True
    return bool(chinese and normalize_name(chinese) in routing_keys)


def walk_topic(
    topic_path: Path,
    *,
    tree: str,
    domain: str,
    references: Path,
    routing_keys: set[str],
) -> list[FolderHit]:
    english, chinese = parse_folder_name(topic_path.name)
    topic_key = _topic_key(english, chinese, topic_path.name)
    topic_label = _topic_label(english, chinese, topic_path.name)
    is_kit_topic = _is_kit_name(english, chinese, topic_path.name)
    in_routing = _topic_in_routing(english, chinese, routing_keys)
    hits = [
        _make_hit(
            topic_path,
            tree=tree,
            domain=domain,
            references=references,
            topic_key=topic_key,
            topic_label=topic_label,
            rel_inside="",
            is_kit_topic=is_kit_topic,
            in_routing=in_routing,
        )
    ]
    for child in iter_subdirs(topic_path):
        rel_inside = child.relative_to(topic_path).as_posix()
        hits.append(
            _make_hit(
                child,
                tree=tree,
                domain=domain,
                references=references,
                topic_key=topic_key,
                topic_label=topic_label,
                rel_inside=rel_inside,
                is_kit_topic=is_kit_topic,
                in_routing=in_routing,
            )
        )
    return hits


def collect_nested_topics(
    root: Path,
    *,
    tree: str,
    references: Path,
    routing_keys: set[str],
) -> list[FolderHit]:
    hits: list[FolderHit] = []
    if not root.is_dir():
        return hits

    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name in SKIP_DIR_NAMES:
            continue
        if child.name == "系统":
            for sub in sorted(child.iterdir(), key=lambda p: p.name):
                if not sub.is_dir() or sub.name in SKIP_DIR_NAMES:
                    continue
                domain = f"系统/{sub.name}"
                for topic in sorted(sub.iterdir(), key=lambda p: p.name):
                    if topic.is_dir() and topic.name not in SKIP_DIR_NAMES:
                        hits.extend(
                            walk_topic(
                                topic,
                                tree=tree,
                                domain=domain,
                                references=references,
                                routing_keys=routing_keys,
                            )
                        )
        elif child.name in DOMAIN_TOPS:
            for topic in sorted(child.iterdir(), key=lambda p: p.name):
                if topic.is_dir() and topic.name not in SKIP_DIR_NAMES:
                    hits.extend(
                        walk_topic(
                            topic,
                            tree=tree,
                            domain=child.name,
                            references=references,
                            routing_keys=routing_keys,
                        )
                    )
        else:
            hits.extend(
                walk_topic(
                    child,
                    tree=tree,
                    domain=child.name,
                    references=references,
                    routing_keys=routing_keys,
                )
            )
    return hits


def collect_api_topics(root: Path, references: Path, routing_keys: set[str]) -> list[FolderHit]:
    hits: list[FolderHit] = []
    if not root.is_dir():
        return hits
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name in SKIP_DIR_NAMES:
            continue
        domain = "非Kit" if child.name in KNOWN_NON_KIT else "API参考"
        hits.extend(
            walk_topic(
                child,
                tree="api",
                domain=domain,
                references=references,
                routing_keys=routing_keys,
            )
        )
    return hits


def _pick_english(hits: list[FolderHit]) -> str:
    both = [hit.english for hit in hits if hit.english and hit.chinese]
    if both:
        return sorted(both, key=len, reverse=True)[0]
    only = [hit.english for hit in hits if hit.english]
    return sorted(only, key=len, reverse=True)[0] if only else ""


def _pick_chinese(hits: list[FolderHit]) -> str:
    names = [hit.chinese for hit in hits if hit.chinese]
    return sorted(names, key=len, reverse=True)[0] if names else ""


def _pick_domain(hits: list[FolderHit]) -> str:
    for tree in ("guide", "skill", "api"):
        for hit in hits:
            if hit.tree != tree:
                continue
            top = hit.domain.split("/")[0]
            if top in DOMAIN_TOPS:
                return hit.domain
    for hit in hits:
        if hit.domain and hit.domain not in {"API参考", "非Kit"}:
            return hit.domain
    return hits[0].domain if hits else ""


def _pick_path(hits: list[FolderHit], tree: str) -> str:
    matched = [hit.relative for hit in hits if hit.tree == tree]
    return sorted(matched, key=len)[0] if matched else ""


def _pick_topic_label(hits: list[FolderHit]) -> str:
    labels = [hit.topic_label for hit in hits if hit.topic_label]
    with_paren = [label for label in labels if "（" in label or "(" in label]
    pool = with_paren or labels
    return sorted(pool, key=len, reverse=True)[0] if pool else ""


def _pick_markdown_titles(hits: list[FolderHit]) -> str:
    """合并三套文档目录中的标题，每个标题占一个单元格行。"""
    titles: list[str] = []
    seen: set[str] = set()
    for tree in ("guide", "skill", "api"):
        for hit in hits:
            if hit.tree != tree:
                continue
            for title in hit.markdown_titles:
                if title not in seen:
                    seen.add(title)
                    titles.append(title)

    value = "\n".join(titles)
    if len(value) <= EXCEL_CELL_LIMIT:
        return value
    suffix = "\n……（标题过多，已截断）"
    return value[: EXCEL_CELL_LIMIT - len(suffix)] + suffix


def _routing_keys(routing_path: Path | None) -> set[str]:
    if routing_path is None or not routing_path.is_file():
        return set()
    keys: set[str] = set()
    for record in parse_kit_routing_file(routing_path):
        keys.add(normalize_name(record.英文))
        if record.中文:
            keys.add(normalize_name(record.中文))
            keys.add(normalize_name(f"{record.英文}({record.中文})"))
    return keys


def merge_hits(hits: list[FolderHit]) -> list[FolderRecord]:
    topic_domains: dict[str, str] = {}
    for hit in hits:
        if hit.depth != 0:
            continue
        current = topic_domains.get(hit.topic_key, "")
        top = hit.domain.split("/")[0]
        if top in DOMAIN_TOPS:
            if hit.tree in {"guide", "skill"}:
                topic_domains[hit.topic_key] = hit.domain
        elif hit.topic_key not in topic_domains:
            topic_domains[hit.topic_key] = hit.domain

    groups: dict[tuple[str, str], list[FolderHit]] = defaultdict(list)
    for hit in hits:
        groups[(hit.topic_key, hit.rel_key)].append(hit)

    records: list[FolderRecord] = []
    for group in groups.values():
        depth = min(hit.depth for hit in group)
        kit_like = any(hit.is_kit_topic for hit in group)
        in_routing = any(hit.in_routing for hit in group)
        if depth == 0:
            kind = "Kit" if kit_like else "非Kit"
        else:
            kind = "子目录"
        topic_key = group[0].topic_key
        records.append(
            FolderRecord(
                领域=topic_domains.get(topic_key) or _pick_domain(group),
                所属主题=_pick_topic_label(group),
                层级=str(depth),
                类型=kind,
                中文=_pick_chinese(group),
                英文=_pick_english(group),
                对应指南=_pick_path(group, "guide"),
                basic_skill=_pick_path(group, "skill"),
                API参考=_pick_path(group, "api"),
                Markdown标题=_pick_markdown_titles(group),
                kit路由="是" if in_routing else "否",
            )
        )

    records.sort(
        key=lambda rec: (
            rec.领域,
            rec.所属主题,
            int(rec.层级) if rec.层级.isdigit() else 0,
            rec.英文.lower() or rec.中文,
            rec.对应指南 or rec.basic_skill or rec.API参考,
        )
    )
    return records


def build_folder_catalog(references: Path, *, routing_path: Path | None = None) -> list[FolderRecord]:
    routing_keys = _routing_keys(routing_path)
    guides = collect_nested_topics(
        references / "harmonyos-guides",
        tree="guide",
        references=references,
        routing_keys=routing_keys,
    )
    skills = collect_nested_topics(
        references / "harmonyos-sdk-basic-skill",
        tree="skill",
        references=references,
        routing_keys=routing_keys,
    )
    apis = collect_api_topics(references / "harmonyos-references", references, routing_keys)
    return merge_hits(guides + skills + apis)
