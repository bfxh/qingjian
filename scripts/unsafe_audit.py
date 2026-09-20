#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""unsafe 增量门：扫 workspace 的 unsafe 块数，对照 docs/review/unsafe-baseline.json。
某个文件超出基线 = 新增了没登记的 unsafe -> 退出码 1（CI 红）。
新增 unsafe 前先读 docs/review/unsafe-audit.md 的纪律，加完登记 + 同步基线。
用法：python3 scripts/unsafe_audit.py [--paths src1 src2 ...]（缺省扫 crates/ apps/ tools/ 下的 *.rs）
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNSAFE = re.compile(r"unsafe\s*(?:\{|fn\b)")
BASELINE_FILE = ROOT / "docs" / "review" / "unsafe-baseline.json"


def main() -> int:
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    defaults = [ROOT / d for d in ("crates", "apps", "tools")]
    roots = [Path(a) for a in sys.argv[1:] if a != "--paths"] or defaults

    counts: dict[str, int] = {}
    for root in roots:
        for path in root.rglob("*.rs"):
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            n = len(UNSAFE.findall(text))
            if n:
                counts[rel] = n

    bad = False
    for rel, n in sorted(counts.items()):
        base = baseline.get(rel, 0)
        if n > base:
            bad = True
            print(
                f"FAIL {rel}: unsafe {base} -> {n}，新增 unsafe 未登记。"
                f"读 docs/review/unsafe-audit.md 的纪律，登记后把 unsafe-baseline.json 的 {rel} 改成 {n}",
                file=sys.stderr,
            )
        elif n < base:
            print(f"NOTE {rel}: unsafe {base} -> {n}，可以顺手把基线降下来")
    if not bad:
        total = sum(counts.values())
        print(f"unsafe audit ok（{len(counts)} 文件 {total} 块，均已在基线内）")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
