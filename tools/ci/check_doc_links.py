#!/usr/bin/env python3
"""检查 Markdown 里的相对链接与锚点：目标文件是否存在、#锚点是否真在那个文件里。

只用标准库。CI 与本地都能跑，退出码非 0 表示有链接失效。

  tools/ci/check_doc_links.py            # 查整个仓库
  tools/ci/check_doc_links.py docs       # 只查某个目录

规则：
- 只查相对链接（http / mailto 跳过，那是外部站点是否还活着的问题，另说）
- 行内代码里的示例链接（`[安装](../x.md)`）不是真链接，跳过
- 目录链接（`docs/`）指向索引页，只要目录在就算过
- 锚点按 GitHub 的规则归一（去标点、小写、空格转连字符）后比对标题
"""

import os
import re
import sys
import unicodedata
import urllib.parse

LINK = re.compile(r'(?<!\!)\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+"[^"]*")?\s*\)')
FENCE = re.compile(r"^(```|~~~)")
SKIP_DIRS = {".git", "target", "node_modules", ".workbuddy"}


def slugify(heading: str) -> str:
    """把标题变成 GitHub 用的锚点：小写、去标点、空格转连字符。"""
    h = heading.strip().lower()
    h = re.sub(r"`([^`]*)`", r"\1", h)
    h = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", h)
    h = re.sub(r"[^\w\- ]", "", h, flags=re.UNICODE)
    return unicodedata.normalize("NFC", h.replace(" ", "-"))


def normalize_anchor(anchor: str) -> str:
    """链接里写的锚点要走同一套归一，否则中文标题里的全角括号 / 连字符会误判。"""
    return slugify(urllib.parse.unquote(anchor).replace("-", " "))


def headings_of(path: str) -> set:
    """收集文件里所有标题的锚点，跳过代码块内的 # 注释行。"""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return set()
    out = set()
    fence = None
    for line in lines:
        m = FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else m.group(1)
            continue
        if fence:
            continue
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            if text:
                out.add(slugify(text))
    return out


def iter_markdown(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".md"):
                yield os.path.join(dirpath, name)


def check(md: str, root: str, cache: dict) -> list:
    """返回这一个文件里的失效链接列表。"""
    bad = []
    rel_md = os.path.relpath(md, root).replace(os.sep, "/")
    with open(md, encoding="utf-8") as f:
        lines = f.read().splitlines()
    fence = None
    for lineno, line in enumerate(lines, 1):
        m = FENCE.match(line)
        if m:
            fence = None if fence == m.group(1) else m.group(1)
            continue
        if fence:
            continue
        scrubbed = re.sub(r"`[^`]*`", "", line)
        for raw in LINK.findall(scrubbed):
            if raw.startswith(("http://", "https://", "mailto:", "<")):
                continue
            parts = raw.split("#", 1)
            rel_path = parts[0]
            anchor = parts[1] if len(parts) > 1 else None
            if not rel_path:
                dest = md
            elif rel_path.startswith("/"):
                dest = os.path.join(root, rel_path.lstrip("/"))
            else:
                dest = os.path.normpath(os.path.join(os.path.dirname(md), rel_path))
            if rel_path.endswith("/"):
                if not os.path.isdir(dest.rstrip("/\\")):
                    bad.append(f"{rel_md}:{lineno}: 目录不存在 -> {raw}")
                continue
            if not os.path.isfile(dest):
                bad.append(f"{rel_md}:{lineno}: 目标不存在 -> {rel_path}")
                continue
            if anchor:
                if dest not in cache:
                    cache[dest] = headings_of(dest)
                if normalize_anchor(anchor) not in cache[dest]:
                    bad.append(f"{rel_md}:{lineno}: 锚点不存在 -> {raw}")
    return bad


def main() -> int:
    args = sys.argv[1:] or ["."]
    cache: dict = {}
    bad: list = []
    checked = 0
    for target in args:
        if os.path.isfile(target):
            bad += check(target, os.path.dirname(target) or ".", cache)
            checked += 1
            continue
        for md in iter_markdown(target):
            bad += check(md, target, cache)
            checked += 1
    print(f"检查了 {checked} 个 Markdown 文件")
    for line in bad:
        print(line)
    if bad:
        print(f"\n{len(bad)} 条链接失效", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())