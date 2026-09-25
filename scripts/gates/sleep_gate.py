"""休眠门：产品代码里 `std::thread::sleep` / `thread::sleep`。

  Rust 的 sleep 跟 Go 一样，轮询等某事发生、循环里 sleep 节流、启动顺序靠 sleep 凑——都会让程序
  在 CI / 弱机器上 flake、在延迟敏感路径上卡顿。正确做法是 channel / 条件变量 / `?` 取消 /
  `tokio::time::sleep` + `select!`。测试里 sleep 等异步就绪是正当的 ⇒ 排除测试面。

  X1 产品代码（排除测试面）出现 `thread::sleep(` —— 棘轮：只准减（新增即红）。

用法：python3 -X utf8 scripts/gates/sleep_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/review/sleep-baseline.json"
SLEEP = re.compile(r"(?:std::)?thread::sleep\s*\(")


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {}
    for rel in gc.rs_files(root, git_tracked):
        if any(t in rel for t in gc.TESTISH) or rel.startswith("tests/"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        n = len(SLEEP.findall(gc.mask(text)))
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    bpath = ROOT / BASELINE
    cur = scan(ROOT, a.git_tracked)
    print(f"SLEEP-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处 thread::sleep）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print("警告：无基线 ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "sleep", bad, shrank)
    return gc.report("SLEEP-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
