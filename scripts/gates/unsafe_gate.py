"""unsafe 块门：产品代码里 `unsafe { … }` 块与 `unsafe fn` / `unsafe impl` 的数量。

  Rust 的 unsafe 是「这块编译器不帮你担保内存安全」——用得越多，未定义行为面越大，reviewer 要
  逐行盯。FFI / 平台后端里 unsafe 是正当的（`ffi` / `sys` / `platform` / `bindings` / 各 OS 壳目录），
  排除；测试也排除。其余代码每多一个 unsafe 块就多一分风险——本门只拦新增。

  X1 产品代码（排除 FFI/平台/测试）unsafe 块数 —— 棘轮：只准减（新增即红）。

用法：python3 -X utf8 scripts/gates/unsafe_gate.py [--git-tracked] [--list] [--write]
"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gates_common as gc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASELINE = "docs/review/unsafe-baseline.json"
# FFI / 平台后端里的 unsafe 是正当的：这些目录不进扫描面
FFI_DIRS = ("/ffi/", "/sys/", "/platform/", "/bindings/", "/macos/", "/windows/",
            "/linux/", "/darwin/", "-sys/")
UNSAFE_BLOCK = re.compile(r"unsafe\s*\{")
UNSAFE_DECL = re.compile(r"\bunsafe\s+(?:fn|impl|trait)\b")


def scan(root: pathlib.Path, git_tracked: bool):
    cur = {}
    for rel in gc.rs_files(root, git_tracked):
        if any(d in rel for d in FFI_DIRS) or rel.startswith("tests/"):
            continue
        if any(t in rel for t in gc.TESTISH):
            continue
        text = gc.read_text(root, rel)
        if not text:
            continue
        masked = gc.mask(text)
        n = len(UNSAFE_BLOCK.findall(masked)) + len(UNSAFE_DECL.findall(masked))
        if n:
            cur[rel] = n
    return cur


def main() -> int:
    ap = gc.add_args(argparse.ArgumentParser())
    a = ap.parse_args()
    bpath = ROOT / BASELINE
    cur = scan(ROOT, a.git_tracked)
    print(f"UNSAFE-GATE count={sum(cur.values())}")
    if a.list:
        for r, n in sorted(cur.items(), key=lambda kv: -kv[1])[:a.top]:
            print(f"  {n:3d}  {r}")
        return 0
    if a.write:
        gc.write_baseline(bpath, cur)
        print(f"已写基线 {BASELINE}（{sum(cur.values())} 处 unsafe 块/声明）——此后只准减")
        return 0
    base = gc.load_baseline(bpath)
    if not base:
        print("警告：无基线 ⇒ 不判；跑 --write 才会管住存量")
    bad, shrank = [], []
    gc.ratchet(cur, base, "unsafe", bad, shrank)
    return gc.report("UNSAFE-GATE", bad, shrank)


if __name__ == "__main__":
    sys.exit(main())
