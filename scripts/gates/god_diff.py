"""上帝对象门：**改基线前先看差**（`--write-baseline` 会一次性重记所有值，等于放松棘轮）。

用法：
  python -X utf8 scripts/gates/god_diff.py               # 只列有差的文件
  python -X utf8 scripts/gates/god_diff.py --all         # 连没变的一起列

为什么要有它（上游实测）：掩码修好后（Rust 生命周期不再被当字符字面量），旧基线里一批文件的
`max_fn_lines` 是**伪小值**。直接 `--write-baseline` 会把「纠正测量」和「真变胖」混着记下去——
先看差才能逐条判断哪条是纠正、哪条是该拦的。

本仓副本相对上游只改路径：脚本搬到 `scripts/gates/`，仓库根是上三级。
"""
import argparse
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
KEYS = ("file_lines", "max_fn_lines", "max_type_members")


def load_gate():
    spec = importlib.util.spec_from_file_location("god_gate_for_diff", ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--git-tracked", action="store_true")
    a = ap.parse_args()
    gg = load_gate()
    root = pathlib.Path(a.root).resolve()
    cfg = gg.load_cfg(root, None)
    files = gg.scan(root, cfg)
    if a.git_tracked:
        import subprocess as _sp
        cp = _sp.run(["git", "ls-files"], cwd=str(root), capture_output=True, text=True,
                     encoding="utf-8", errors="replace", shell=False)
        tracked = set(cp.stdout.split())
        files = {k: v for k, v in files.items() if k in tracked}
    base = gg.load_baseline(root / cfg["baseline"])
    rows = []
    for rel, m in files.items():
        b = base.get(rel)
        if b is None:
            rows.append((rel, "（新增文件）", {k: (None, m[k]) for k in KEYS}))
            continue
        d = {k: (b.get(k, 0), m[k]) for k in KEYS if b.get(k, 0) != m[k]}
        if d or a.all:
            rows.append((rel, "", d))
    rows.sort(key=lambda r: -max((abs((v[1] or 0) - (v[0] or 0)) for v in r[2].values()), default=0))
    for rel, note, d in rows:
        parts = []
        for k, (o, n) in d.items():
            arrow = "↑" if (o is not None and n > o) else ("↓" if o is not None else "+")
            parts.append(f"{k} {o}→{n}{arrow}")
        print(f"  {rel}{note}　" + "　".join(parts))
    print(f"共 {len(rows)} 个条目有差（扫描 {len(files)} 个文件，基线 {len(base)} 条）")
    up = [r for r in rows if any(o is not None and n > o for o, n in r[2].values())]
    print(f"其中含「变大」的 {len(up)} 条 —— 逐条判断是「纠正测量」还是「真变胖」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
