"""忽略结果门：产品代码里显式丢弃值——`let _ = expr;` 或 `let (a, _) = f()` / `let (_, b) = f()`
这类含 `_` 的解构赋值。

  Rust 里 `let _ = result;` 是明确「我不在乎这个结果」——绝大多数情况是吞掉了 `Result` 里的错误
  （与 Go 的 errcheck、本仓 arch 门的 panic!/todo! 同一类「静默忽略」）。编译器不报。测试里
  丢弃无害 ⇒ 排除测试面。`let _x = …`（把值绑给 `_x`）是正常命名，不算丢弃。

  X1 产品代码（排除测试面）出现 `let _ =` / 含 `_` 的解构赋值 —— 棘轮：只准减（新增即红）。

用法：python3 -X utf8 scripts/gates/ignore_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/review/ignore-baseline.json"
# `let _ =` 或 `let (... _ ... ) =`（解构里含丢弃位）
IGNORE = re.compile(r"^\s*let\s+(?:_\s*=|\([^;]*\b_\b[^;]*\)\s*=)")


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {}
    for rel in gc.rs_files(root, git_tracked):
        if any(t in rel for t in gc.TESTISH) or rel.startswith("tests/"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        n = 0
        for line in gc.mask(text).splitlines():
            if IGNORE.match(line):
                n += 1
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    bpath = ROOT / BASELINE
    cur = scan(ROOT, a.git_tracked)
    print(f"IGNORE-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处忽略结果）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print("警告：无基线 ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "ignore", bad, shrank)
    return gc.report("IGNORE-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
