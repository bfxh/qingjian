"""unwrap/expect 门：产品代码里 `.unwrap()` / `.expect()` / `.unwrap_err()` / `.expect_err()` /
`.unwrap_unchecked()` / `.expect_unchecked()` 这类「把 Result/Option 当必定成功」的调用。

  Rust 里 `?` 才是正确传播错误的方式；`unwrap`/`expect` 一旦遇到 Err/None 就直接 panic，把库里的
  一个可恢复错误变成整个进程崩溃。编译器不报，但这是 Rust 头号坏味道（clippy 只是 warn，不拦）。
  测试里 `assert!(x.unwrap())` 是正当写法 ⇒ 排除测试面。

  X1 产品代码（排除测试面）出现 unwrap/expect 系列 —— 棘轮：只准减（新增即红）。

用法：python3 -X utf8 scripts/gates/unwrap_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/review/unwrap-baseline.json"
UNWRAP = re.compile(
    r"\.(?:unwrap|expect|unwrap_err|expect_err|unwrap_unchecked|expect_unchecked)\s*\(")


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {}
    for rel in gc.rs_files(root, git_tracked):
        if any(t in rel for t in gc.TESTISH) or rel.startswith("tests/"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        n = len(UNWRAP.findall(gc.mask(text)))
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    bpath = ROOT / BASELINE
    cur = scan(ROOT, a.git_tracked)
    print(f"UNWRAP-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处 unwrap/expect）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print("警告：无基线 ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "unwrap", bad, shrank)
    return gc.report("UNWRAP-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
