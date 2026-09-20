#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""注释残留门：代码注释里不允许留下未落地的标记（TODO / FIXME / HACK / XXX）。
2026-09-20 全仓存量清零后启用的锁。文档（.md，含 docs/plan/todo.md 规划清单）不算；
脚本与配置文件里只有注释行才查，字符串字面量不查，避免误伤代码里的说明文字。
用法：python3 scripts/detect_todos.py"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"target", ".git", ".local", ".cargo", ".pytest_cache", "__pycache__"}
PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
# 只查这些后缀的**注释行**；.md / .json / .iss 豁免（文档可写待办，数据文件没有注释）
COMMENT_PREFIXES = {
    ".rs": "//",
    ".py": "#",
    ".toml": "#",
    ".yml": "#",
    ".yaml": "#",
    ".sh": "#",
    ".ps1": "#",
}


def main() -> int:
    bad: list[str] = []
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            path = Path(root) / name
            if path.suffix not in COMMENT_PREFIXES:
                continue
            rel = path.relative_to(ROOT).as_posix()
            prefix = COMMENT_PREFIXES[path.suffix]
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith(prefix) and PATTERN.search(stripped):
                    bad.append(f"{rel}:{i}: {stripped}")
    if bad:
        print("发现注释里未落地的 TODO / FIXME / HACK / XXX：", file=sys.stderr)
        for b in bad[:50]:
            print("  " + b, file=sys.stderr)
        if len(bad) > 50:
            print(f"  …共 {len(bad)} 处", file=sys.stderr)
        return 1
    print("注释残留扫描通过（零命中）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
