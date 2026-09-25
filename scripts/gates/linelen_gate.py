"""行长门：单行超过阈值（默认 200 字符）即记一笔。语言无关，纯行长度，无需掩码。

  Go/Rust 官方都不强制行长，但超长行在 review / diff / 终端里都难读，也常是「一个表达式塞了
  太多东西」或「超长字符串字面量 / 宏」的信号。本门不要求立刻修存量，只拦**新增**的超长行——
  改文件时顺手断行即可。

  X1 任意 .rs 文件里存在超过 `MAX`（默认 200）字符的行 —— 棘轮：只准减。

用法：python3 -X utf8 scripts/gates/linelen_gate.py [--git-tracked] [--list] [--write] [--max 200]
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/review/linelen-baseline.json"
MAX = 200


def scan(root: pathlib.Path, git_tracked: bool, maxlen: int):
    cur = {}
    for rel in gc.rs_files(root, git_tracked):
        text = gc.read_text(root, rel)
        if not text:
            continue
        n = sum(1 for ln in text.splitlines() if len(ln) > maxlen)
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    ap.add_argument("--max", type=int, default=MAX)
    a = ap.parse_args()
    bpath = ROOT / BASELINE
    cur = scan(ROOT, a.git_tracked, a.max)
    print(f"LINELEN-GATE(>{a.max}) count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 行>{a.max} 字符）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print("警告：无基线 ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "linelen", bad, shrank)
    return gc.report("LINELEN-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
