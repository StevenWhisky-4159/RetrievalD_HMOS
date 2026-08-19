#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对照文档库实际 Kit 目录与 kit-routing.md / Excel 覆盖情况。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from .parser import KitRecord, parse_kit_routing_file, split_kit_name  # type: ignore[import-not-found]
except ImportError:
    from parser import KitRecord, parse_kit_routing_file, split_kit_name  # noqa: E402

_REPO = _HERE.parents[2]
REFERENCES = _REPO / "harmonyos-sdk-coding-basic-skill" / "references"
DEFAULT_ROUTING = REFERENCES / "kit-routing.md"

GUIDES_ROOT = REFERENCES / "harmonyos-guides"
SKILL_ROOT = REFERENCES / "harmonyos-sdk-basic-skill"
API_ROOT = REFERENCES / "harmonyos-references"

# 指南/basic skill 中，Kit 目录通常在领域下一层；系统领域再多一层子领域。
GUIDE_DOMAIN_DIRS = {"AI", "图形", "媒体", "应用框架", "应用服务", "系统"}
SYSTEM_SUBDOMAINS = {"基础功能", "安全", "硬件", "网络", "调测调优"}

# API 参考顶层中明确不是 Kit 的目录
API_NON_KIT_DIRS = {
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
    "ArkTS API",
    "开发说明",
    "系统能力SystemCapability使用指南",
    "通用错误码",
    "附录",
}

KITISH_RE = re.compile(r"(Kit|ArkUI|ArkTS|ArkWeb|ArkData|ArkGraphics|AR Engine)", re.IGNORECASE)
PAREN_RE = re.compile(r"[（(].+[）)]$")
NO_DIR_HINTS = ("无独立目录", "无")


def _norm(name: str) -> str:
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


def _looks_like_kit_dir(name: str) -> bool:
    if name in API_NON_KIT_DIRS:
        return False
    if PAREN_RE.search(name) and KITISH_RE.search(name):
        return True
    if name.endswith("Kit") or " Kit" in name:
        return True
    return bool(KITISH_RE.search(name) and PAREN_RE.search(name))


def _collect_kit_dirs(root: Path, *, nested_domains: bool) -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not root.is_dir():
        return found

    if not nested_domains:
        for child in root.iterdir():
            if child.is_dir() and _looks_like_kit_dir(child.name):
                found[child.name] = child
        return found

    for domain in root.iterdir():
        if not domain.is_dir() or domain.name not in GUIDE_DOMAIN_DIRS:
            continue
        if domain.name == "系统":
            for sub in domain.iterdir():
                if not sub.is_dir():
                    continue
                for kit in sub.iterdir():
                    if kit.is_dir() and _looks_like_kit_dir(kit.name):
                        found[kit.name] = kit
        else:
            for kit in domain.iterdir():
                if kit.is_dir() and _looks_like_kit_dir(kit.name):
                    found[kit.name] = kit
    return found


def _path_exists(relative: str) -> bool | None:
    text = relative.strip()
    if not text or any(hint in text for hint in NO_DIR_HINTS):
        return None
    candidate = REFERENCES / text.replace("\\", "/")
    return candidate.is_dir() or candidate.is_file()


def _index_by_norm(names: dict[str, Path]) -> dict[str, str]:
    index: dict[str, str] = {}
    for name in names:
        index[_norm(name)] = name
        english, chinese = split_kit_name(name)
        index[_norm(english)] = name
        if chinese:
            index[_norm(chinese)] = name
            index[_norm(f"{english}({chinese})")] = name
    return index


def _match_dir(query: str, index: dict[str, str]) -> str | None:
    keys = [
        _norm(query),
        _norm(split_kit_name(query)[0]),
        _norm(split_kit_name(query)[1]),
    ]
    for key in keys:
        if key and key in index:
            return index[key]
    return None


def check_coverage(records: list[KitRecord]) -> dict:
    guide_dirs = _collect_kit_dirs(GUIDES_ROOT, nested_domains=True)
    skill_dirs = _collect_kit_dirs(SKILL_ROOT, nested_domains=True)
    api_dirs = _collect_kit_dirs(API_ROOT, nested_domains=False)

    guide_index = _index_by_norm(guide_dirs)
    skill_index = _index_by_norm(skill_dirs)
    api_index = _index_by_norm(api_dirs)

    routing_keys: set[str] = set()
    missing_in_lib: list[dict] = []
    path_missing: list[dict] = []
    covered: list[dict] = []

    for rec in records:
        display = f"{rec.英文}（{rec.中文}）" if rec.中文 else rec.英文
        routing_keys.add(_norm(rec.英文))
        routing_keys.add(_norm(display))
        if rec.中文:
            routing_keys.add(_norm(rec.中文))
            routing_keys.add(_norm(f"{rec.英文}({rec.中文})"))

        g = _match_dir(display, guide_index)
        s = _match_dir(display, skill_index)
        a = _match_dir(display, api_index)

        expected_no_guide = any(hint in rec.对应指南 for hint in NO_DIR_HINTS)
        expected_no_skill = any(hint in rec.basic_skill for hint in NO_DIR_HINTS)

        gaps = []
        if not g and not expected_no_guide:
            gaps.append("指南目录")
        if not s and not expected_no_skill:
            gaps.append("basic skill 目录")
        if not a:
            gaps.append("API参考目录")

        guide_path_ok = _path_exists(rec.对应指南)
        skill_path_ok = _path_exists(rec.basic_skill)
        api_path_ok = _path_exists(rec.API参考)

        path_gaps = []
        if guide_path_ok is False:
            path_gaps.append("对应指南")
        if skill_path_ok is False:
            path_gaps.append("basic skill")
        if api_path_ok is False:
            path_gaps.append("API参考")

        row = {
            "领域": rec.领域,
            "中文": rec.中文,
            "英文": rec.英文,
            "指南目录": g or "",
            "skill目录": s or "",
            "API目录": a or "",
            "路由指南路径存在": guide_path_ok,
            "路由skill路径存在": skill_path_ok,
            "路由API路径存在": api_path_ok,
        }
        if gaps:
            row["缺失"] = gaps
            missing_in_lib.append(row)
        else:
            covered.append(row)
        if path_gaps:
            row_path = dict(row)
            row_path["路径不存在"] = path_gaps
            row_path["对应指南"] = rec.对应指南
            row_path["basic skill"] = rec.basic_skill
            row_path["API参考"] = rec.API参考
            path_missing.append(row_path)

    extra_guides = sorted(
        name for name in guide_dirs if _norm(name) not in routing_keys and _norm(split_kit_name(name)[0]) not in routing_keys
    )
    extra_skills = sorted(
        name for name in skill_dirs if _norm(name) not in routing_keys and _norm(split_kit_name(name)[0]) not in routing_keys
    )
    extra_apis = sorted(
        name for name in api_dirs if _norm(name) not in routing_keys and _norm(split_kit_name(name)[0]) not in routing_keys
    )

    # 指南/skill 里非 Kit 顶层目录（可能漏扫）
    extra_top_guides = sorted(
        p.name for p in GUIDES_ROOT.iterdir() if p.is_dir() and p.name not in GUIDE_DOMAIN_DIRS
    )
    extra_top_skills = sorted(
        p.name for p in SKILL_ROOT.iterdir() if p.is_dir() and p.name not in GUIDE_DOMAIN_DIRS
    )

    return {
        "routing_kit_count": len(records),
        "lib_guide_kit_count": len(guide_dirs),
        "lib_skill_kit_count": len(skill_dirs),
        "lib_api_kit_count": len(api_dirs),
        "fully_covered_count": len(covered),
        "missing_dir_count": len(missing_in_lib),
        "routing_path_missing_count": len(path_missing),
        "missing_in_library": missing_in_lib,
        "routing_path_not_found": path_missing,
        "library_kits_not_in_routing": {
            "指南": extra_guides,
            "basic skill": extra_skills,
            "API参考": extra_apis,
        },
        "non_kit_top_dirs": {
            "指南": extra_top_guides,
            "basic skill": extra_top_skills,
            "API参考非Kit": sorted(API_NON_KIT_DIRS & {p.name for p in API_ROOT.iterdir() if p.is_dir()}),
        },
        "lib_guide_kits": sorted(guide_dirs),
        "lib_skill_kits": sorted(skill_dirs),
        "lib_api_kits": sorted(api_dirs),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查文档库 Kit 是否被 kit-routing 覆盖")
    parser.add_argument("--routing", type=Path, default=DEFAULT_ROUTING)
    parser.add_argument("--json-out", type=Path, default=_HERE / "data" / "kit_coverage_report.json")
    return parser.parse_args()


def _rel(path: Path) -> Path:
    return path if path.is_absolute() else (_REPO / path)


def main() -> int:
    args = parse_args()
    routing = _rel(args.routing)
    records = parse_kit_routing_file(routing)
    report = check_coverage(records)

    json_out = _rel(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[ok] routing Kit 数: {report['routing_kit_count']}")
    print(f"[ok] 文档库 Kit 目录: 指南 {report['lib_guide_kit_count']} / basic skill {report['lib_skill_kit_count']} / API {report['lib_api_kit_count']}")
    print(f"[ok] 三库目录均覆盖: {report['fully_covered_count']}")
    print(f"[!!] routing 有、文档库缺目录: {report['missing_dir_count']}")
    print(f"[!!] routing 填写路径在磁盘不存在: {report['routing_path_missing_count']}")

    extras = report["library_kits_not_in_routing"]
    print(f"[!!] 文档库有、routing 未收录: 指南 {len(extras['指南'])} / skill {len(extras['basic skill'])} / API {len(extras['API参考'])}")
    for bucket, names in extras.items():
        for name in names:
            print(f"     未收录[{bucket}]: {name}")

    for row in report["missing_in_library"]:
        print(f"     缺目录: {row['英文']}（{row['中文']}） -> {', '.join(row['缺失'])}")

    # 路径不存在只打印摘要，避免刷屏
    by_col: dict[str, int] = defaultdict(int)
    for row in report["routing_path_not_found"]:
        for col in row["路径不存在"]:
            by_col[col] += 1
    if by_col:
        print("[!!] 路径不存在分类:", dict(by_col))
        for row in report["routing_path_not_found"][:8]:
            print(f"     路径缺失样例: {row['英文']} {row['路径不存在']}")
            if "API参考" in row["路径不存在"]:
                print(f"       API={row['API参考']}")

    print(f"[ok] 报告: {json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
