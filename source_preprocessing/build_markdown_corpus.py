#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 mistune AST 将 Markdown 按标题章节转换为纯文本和代码 JSONL 语料。

处理规则：
- 标题保存完整层级列表，并移除 **、`code` 等 Markdown 标记。
- 正文转换为纯文本，保留段落、列表和表格的文本结构。
- fenced/indented 代码块不进入正文，改为写入独立代码语料。
- 行内代码保留在正文中参与普通分词，同时原样写入独立代码语料。
- 删除图片和 HTML；链接仅保留可见文本，不保留 URL。
- 文件开头由三条或更多横线包围的 metadata/frontmatter 会先移除，
  不会被 mistune 当作 Setext 标题。
- 首个标题前的正文使用 frontmatter.title、首个标题或文件名作为标题。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import mistune

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from .parser import parse_folder_name  # type: ignore[import-not-found]
except ImportError:
    from parser import parse_folder_name  # noqa: E402

_REPO = _HERE.parents[2]
DEFAULT_REFERENCES = _REPO / "harmonyos-sdk-coding-basic-skill" / "references"
DEFAULT_OUTPUT = _HERE.parent / "indexing" / "data" / "markdown_paragraph_corpus.jsonl"
DEFAULT_CODE_OUTPUT = _HERE.parent / "indexing" / "data" / "markdown_code_corpus.jsonl"

EXCLUDE_FILES = {"INDEX.md", "kit-routing.md", "feature-routing.md"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
FRONTMATTER_BOUNDARY_RE = re.compile(r"^\s*-{3,}\s*$")
FRONTMATTER_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$")
HORIZONTAL_SPACE_RE = re.compile(r"[ \t]+")
RAW_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MARKDOWN_ESCAPE_RE = re.compile(r"\\([\\`*{}\[\]()#+\-.!_>])")
STRONG_ASTERISK_RE = re.compile(r"\*\*([^*\n]+?)\*\*")
STRONG_UNDERSCORE_RE = re.compile(r"__([^_\n]+?)__")

MARKDOWN = mistune.create_markdown(
    renderer="ast",
    plugins=["table", "strikethrough", "task_lists"],
)

SKIP_TOKEN_TYPES = {
    "block_code",
    "block_html",
    "inline_html",
    "image",
    "thematic_break",
    "blank_line",
}


@dataclass(frozen=True)
class CodeBlock:
    code: str
    style: str
    info: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "style": self.style,
            "info": self.info,
        }


@dataclass(frozen=True)
class SectionChunk:
    directory_chinese: str
    directory_english: str
    path: str
    titles: tuple[str, ...]
    original: str
    block_code: tuple[CodeBlock, ...]
    inline_code: tuple[str, ...]

    def to_dict(self, chunk_id: int) -> dict[str, int | str | list[str]]:
        return {
            "chunk_id": chunk_id,
            "所属子目录中文": self.directory_chinese,
            "所属子目录英文": self.directory_english,
            "路径": self.path,
            "标题": list(self.titles),
            "原文": self.original,
        }

    def code_to_dict(
        self,
        code_chunk_id: int,
        text_chunk_id: int | None,
    ) -> dict[str, int | None | str | list[str] | list[dict[str, str]]]:
        return {
            "code_chunk_id": code_chunk_id,
            "text_chunk_id": text_chunk_id,
            "所属子目录中文": self.directory_chinese,
            "所属子目录英文": self.directory_english,
            "路径": self.path,
            "标题": list(self.titles),
            "block_code": [block.to_dict() for block in self.block_code],
            "inline_code": list(self.inline_code),
        }


def strip_markdown_links(text: str) -> str:
    """容错清理未被 mistune 识别的内联链接，保留 label、删除 URL。"""
    result: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "[":
            result.append(text[index])
            index += 1
            continue

        label_end = text.find("]", index + 1)
        if label_end < 0 or label_end + 1 >= length or text[label_end + 1] != "(":
            result.append(text[index])
            index += 1
            continue

        target_start = label_end + 2
        target_end = None
        if target_start < length and text[target_start] == "<":
            closing = text.find(">)", target_start + 1)
            if closing >= 0:
                target_end = closing + 2
        else:
            depth = 1
            cursor = target_start
            while cursor < length:
                char = text[cursor]
                if char == "\\":
                    cursor += 2
                    continue
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        target_end = cursor + 1
                        break
                cursor += 1

        if target_end is None:
            line_end = text.find("\n", target_start)
            if line_end < 0:
                line_end = length
            closing = text.rfind(")", target_start, line_end)
            if closing >= 0:
                target_end = closing + 1
            else:
                result.append(text[index])
                index += 1
                continue

        label = text[index + 1 : label_end]
        result.append(MARKDOWN_ESCAPE_RE.sub(r"\1", label))
        index = target_end

    return RAW_URL_RE.sub("", "".join(result))


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """移除文件开头由 3 个或更多横线包围的 metadata 块。"""
    text = content.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or not FRONTMATTER_BOUNDARY_RE.fullmatch(lines[0].rstrip("\r\n")):
        return {}, text

    end_index = None
    for index in range(1, len(lines)):
        if FRONTMATTER_BOUNDARY_RE.fullmatch(lines[index].rstrip("\r\n")):
            end_index = index
            break
    if end_index is None:
        return {}, text

    metadata: dict[str, str] = {}
    for line in lines[1:end_index]:
        matched = FRONTMATTER_FIELD_RE.match(line.rstrip("\r\n"))
        if not matched:
            continue
        key = matched.group(1)
        value = _strip_quotes(matched.group(2))
        if value:
            metadata[key] = value
    return metadata, "".join(lines[end_index + 1 :])


def _clean_lines(text: str) -> str:
    text = strip_markdown_links(text)
    text = STRONG_ASTERISK_RE.sub(r"\1", text)
    text = STRONG_UNDERSCORE_RE.sub(r"\1", text)
    lines = [
        HORIZONTAL_SPACE_RE.sub(" ", line).strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    compact: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line
        if blank and previous_blank:
            continue
        compact.append(line)
        previous_blank = blank
    return "\n".join(compact)


def token_text(token: dict) -> str:
    """递归提取 AST token 的可见纯文本。"""
    token_type = token.get("type", "")
    if token_type in SKIP_TOKEN_TYPES:
        return ""
    if token_type in {"text", "codespan"}:
        return str(token.get("raw", ""))
    if token_type in {"linebreak", "softbreak"}:
        return "\n"

    children = token.get("children")
    if not isinstance(children, list):
        return str(token.get("raw", "")) if token_type not in SKIP_TOKEN_TYPES else ""

    if token_type in {"table_head", "table_row"}:
        return " | ".join(
            value
            for child in children
            if (value := _clean_lines(token_text(child)))
        )
    if token_type in {"list", "table", "table_body", "block_quote"}:
        separator = "\n"
    elif token_type == "list_item":
        separator = "\n"
    else:
        separator = ""
    return separator.join(token_text(child) for child in children)


def block_text(token: dict) -> str:
    token_type = token.get("type", "")
    if token_type in SKIP_TOKEN_TYPES or token_type == "heading":
        return ""
    return _clean_lines(token_text(token))


def collect_code(
    token: dict,
    block_codes: list[CodeBlock],
    inline_codes: list[str],
) -> None:
    """递归收集块级代码和行内代码，并保留块级代码元数据。"""
    token_type = token.get("type", "")
    if token_type == "block_code":
        raw = token.get("raw", "")
        attrs = token.get("attrs", {})
        block_codes.append(
            CodeBlock(
                code=str(raw),
                style=str(token.get("style", "")),
                info=(
                    str(attrs.get("info", ""))
                    if isinstance(attrs, dict)
                    else ""
                ),
            )
        )
        return
    if token_type == "codespan":
        inline_codes.append(str(token.get("raw", "")))
        return

    children = token.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                collect_code(child, block_codes, inline_codes)


def clean_inline_markdown(value: str) -> str:
    """使用同一 mistune 解析器清理 frontmatter 中可能存在的 Markdown 样式。"""
    ast = MARKDOWN(f"# {value}")
    for token in ast:
        if token.get("type") == "heading":
            return _clean_lines(token_text(token))
    return _clean_lines(value)


def document_title(markdown_path: Path, metadata: dict[str, str], ast: list[dict]) -> str:
    frontmatter_title = clean_inline_markdown(metadata.get("title", ""))
    if frontmatter_title:
        return frontmatter_title

    first_heading = ""
    for token in ast:
        if token.get("type") != "heading":
            continue
        title = _clean_lines(token_text(token))
        if not title:
            continue
        if not first_heading:
            first_heading = title
        if token.get("attrs", {}).get("level") == 1:
            return title
    return first_heading or markdown_path.stem


def split_markdown_sections(
    ast: list[dict],
    fallback_title: str,
) -> Iterator[
    tuple[tuple[str, ...], str, tuple[CodeBlock, ...], tuple[str, ...]]
]:
    """按 AST heading 边界返回标题、正文、块级代码和行内代码。"""
    current_titles = (fallback_title,)
    heading_stack: dict[int, str] = {}
    blocks: list[str] = []
    block_codes: list[CodeBlock] = []
    inline_codes: list[str] = []

    def flush() -> (
        tuple[tuple[str, ...], str, tuple[CodeBlock, ...], tuple[str, ...]]
        | None
    ):
        original = _clean_lines("\n\n".join(blocks))
        blocks.clear()
        current_block_codes = tuple(block_codes)
        current_inline_codes = tuple(inline_codes)
        block_codes.clear()
        inline_codes.clear()
        if not original and not current_block_codes and not current_inline_codes:
            return None
        return (
            current_titles,
            original,
            current_block_codes,
            current_inline_codes,
        )

    for token in ast:
        if token.get("type") == "heading":
            chunk = flush()
            if chunk is not None:
                yield chunk

            title = _clean_lines(token_text(token))
            level = int(token.get("attrs", {}).get("level", 1))
            if title:
                for old_level in tuple(heading_stack):
                    if old_level >= level:
                        del heading_stack[old_level]
                heading_stack[level] = title
                current_titles = tuple(
                    heading_stack[active_level]
                    for active_level in sorted(heading_stack)
                )
            collect_code(token, block_codes, inline_codes)
            continue

        collect_code(token, block_codes, inline_codes)
        text = block_text(token)
        if text:
            blocks.append(text)

    chunk = flush()
    if chunk is not None:
        yield chunk


def iter_markdown_files(references: Path, *, sub_skill_only: bool = False) -> Iterator[Path]:
    basic_skill_root = references / "harmonyos-sdk-basic-skill"
    for dirpath, dirnames, filenames in os.walk(references):
        dirnames.sort()
        filenames.sort()
        parent = Path(dirpath)
        for filename in filenames:
            path = parent / filename
            if path.suffix.lower() not in MARKDOWN_SUFFIXES or filename in EXCLUDE_FILES:
                continue
            if sub_skill_only:
                try:
                    path.relative_to(basic_skill_root)
                    inside_basic_skill = True
                except ValueError:
                    inside_basic_skill = False
                if inside_basic_skill and filename != "SUB_SKILL.md":
                    continue
            yield path


def read_markdown_text(path: Path) -> str:
    """读取 Markdown；Windows 下显式启用扩展长度路径。"""
    file_path = str(path.resolve())
    if sys.platform == "win32" and not file_path.startswith("\\\\?\\"):
        file_path = "\\\\?\\" + file_path
    with open(file_path, "r", encoding="utf-8", errors="replace") as source:
        return source.read()


def iter_file_chunks(markdown_path: Path, references: Path) -> Iterator[SectionChunk]:
    try:
        content = read_markdown_text(markdown_path)
    except OSError as error:
        print(f"[warn] 读取失败: {markdown_path}: {error}", file=sys.stderr)
        return

    metadata, body = parse_frontmatter(content)
    ast = MARKDOWN(body)
    title = document_title(markdown_path, metadata, ast)
    directory_english, directory_chinese = parse_folder_name(markdown_path.parent.name)
    relative_path = markdown_path.relative_to(references).as_posix()

    for headings, original, block_code, inline_code in split_markdown_sections(
        ast,
        title,
    ):
        yield SectionChunk(
            directory_chinese=directory_chinese,
            directory_english=directory_english,
            path=relative_path,
            titles=headings or (title,),
            original=original,
            block_code=block_code,
            inline_code=inline_code,
        )


def write_corpus(
    references: Path,
    output_path: Path,
    code_output_path: Path | None = None,
    *,
    sub_skill_only: bool = False,
) -> tuple[int, int, int]:
    if code_output_path is None:
        code_output_path = output_path.with_name(DEFAULT_CODE_OUTPUT.name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    code_output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    code_temporary_path = code_output_path.with_suffix(code_output_path.suffix + ".tmp")
    file_count = 0
    files_with_chunks = 0
    chunk_count = 0
    code_chunk_count = 0

    with (
        temporary_path.open("w", encoding="utf-8", newline="\n") as output,
        code_temporary_path.open("w", encoding="utf-8", newline="\n") as code_output,
    ):
        for markdown_path in iter_markdown_files(references, sub_skill_only=sub_skill_only):
            file_count += 1
            current_file_chunks = 0
            for chunk in iter_file_chunks(markdown_path, references):
                text_chunk_id: int | None = None
                if chunk.original:
                    text_chunk_id = chunk_count
                    output.write(
                        json.dumps(
                            chunk.to_dict(chunk_count),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
                    output.write("\n")
                    chunk_count += 1
                    current_file_chunks += 1
                code_output.write(
                    json.dumps(
                        chunk.code_to_dict(code_chunk_count, text_chunk_id),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                code_output.write("\n")
                code_chunk_count += 1
            if current_file_chunks:
                files_with_chunks += 1
            if file_count % 1000 == 0:
                print(f"[info] Markdown {file_count}，分片 {chunk_count}", flush=True)

    temporary_path.replace(output_path)
    code_temporary_path.replace(code_output_path)
    return file_count, files_with_chunks, chunk_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用 mistune 构建纯文本与代码章节 JSONL 语料")
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES, help="references 根目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 JSONL 路径")
    parser.add_argument(
        "--code-output",
        type=Path,
        default=DEFAULT_CODE_OUTPUT,
        help="代码 JSONL 输出路径",
    )
    parser.add_argument(
        "--basic-skill-sub-skill-only",
        action="store_true",
        help="basic skill 目录只收录 SUB_SKILL.md，与现有 build_index.py 行为一致",
    )
    return parser.parse_args()


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (_REPO / path)


def main() -> int:
    args = parse_args()
    references = _resolve_path(args.references)
    output_path = _resolve_path(args.output)
    code_output_path = _resolve_path(args.code_output)
    if not references.is_dir():
        print(f"[error] references 不存在: {references}", file=sys.stderr)
        return 1

    started = time.time()
    files, files_with_chunks, chunks = write_corpus(
        references,
        output_path,
        code_output_path,
        sub_skill_only=args.basic_skill_sub_skill_only,
    )
    print(f"[ok] Markdown 文件: {files}")
    print(f"[ok] 有效文件: {files_with_chunks}")
    print(f"[ok] 章节分片: {chunks}")
    print(f"[ok] JSONL: {output_path} ({output_path.stat().st_size / 1024 / 1024:.2f} MB)")
    print(
        f"[ok] 代码 JSONL: {code_output_path} "
        f"({code_output_path.stat().st_size / 1024 / 1024:.2f} MB)"
    )
    print(f"[ok] 耗时: {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
