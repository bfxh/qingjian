"""圈复杂度门：函数内分支点数量（纯文本启发式，Rust 感知掩码）。

  决策点 = 1（函数本身）+ `if`/`for`/`while`/`loop`/`match` 各 +1 + `&&`/`||` 各 +1 +
  `?` 试运算符各 +1 + `match` 每个分支 `=>` 各 +1。只判产品代码（测试 setup 函数复杂度高是
  常态，不算产品风险）——与 clippy 的 cyclomatic_complexity 同思路，但用纯文本、不依赖编译。

  X1 函数圈复杂度 >15 —— 棘轮；>50（几乎无法单测覆盖）—— 棘轮。按文件记「超 15 的函数数 /
  超 50 的函数数」。

用法：python3 -X utf8 scripts/gates/cyc_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/review/cyc-baseline.json"
FN_DECLARE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+|async\s+|unsafe\s+|extern\s+)*fn\s+[A-Za-z_]")
KW = re.compile(r"\b(if|for|while|loop|match)\b")
ANDOR = re.compile(r"&&|\|\|")
QUEST = re.compile(r"(?<![:\w<])\?(?![A-Za-z_])")
ARMS = re.compile(r"=>")


def fn_cc(body: str) -> int:
    return 1 + len(KW.findall(body)) + len(ANDOR.findall(body)) \
        + len(QUEST.findall(body)) + len(ARMS.findall(body))


def scan(root: pathlib.Path, git_tracked: bool):
    over15, over50 = {}, {}
    for rel in gc.rs_files(root, git_tracked):
        if any(t in rel for t in gc.TESTISH) or rel.startswith("tests/"):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        lines = gc.mask(text).splitlines()
        c15 = c50 = 0
        for i, line in enumerate(lines):
            if not FN_DECLARE.match(line):
                continue
            depth, started, end = 0, False, i
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if "{" in lines[j]:
                    started = True
                if started and depth <= 0:
                    end = j
                    break
            body = "\n".join(lines[i:end + 1])
            cc = fn_cc(body)
            if cc > 15:
                c15 += 1
            if cc > 50:
                c50 += 1
        if c15:
            over15[rel] = c15
        if c50:
            over50[rel] = c50
    return {"over15": over15, "over50": over50}


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    bpath = ROOT / BASELINE
    cur = scan(ROOT, a.git_tracked)
    print(f"CYC-GATE >15={sum(cur['over15'].values())} >50={sum(cur['over50'].values())}")
    if a.list:
        for k, d in (("over15", cur["over15"]), ("over50", cur["over50"])):
            for r, n in sorted(d.items(), key=lambda kv: -kv[1])[:a.top]:
                print(f"  {k:7s} {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（>15={sum(cur['over15'].values())} / >50={sum(cur['over50'].values())}）——此后只准减")
        return 0
    base = gc.load_baseline(bpath) or {"over15": {}, "over50": {}}
    if not base:
        print("警告：无基线 ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur["over15"], base.get("over15", {}), "cyc>15", bad, shrank)
    gc.ratchet(cur["over50"], base.get("over50", {}), "cyc>50", bad, shrank)
    return gc.report("CYC-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
