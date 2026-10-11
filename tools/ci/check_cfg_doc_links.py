#!/usr/bin/env python3
"""找「文档链接指向 cfg 门控模块」的地方——rustdoc 在本地抓不到、只有 CI 才炸的那一类。

为什么需要它：文档里写 [`pipe`] 这样指向模块的链接时，如果那个模块带着
`#[cfg(windows)]`，那么在 Windows 上 `cargo doc` 一切正常，换到 Linux runner 就报
`unresolved link to pipe`；反过来带 `#[cfg(target_os = "macos")]` 的模块在 Linux 上
也照样看不见。也就是说：**这类链接能不能解析，取决于构建文档的那台机器支持哪些 cfg**，
本地永远只能验到自己那半边。

所以改成静态扫：不依赖 cargo，直接把「被 cfg 门控的 mod 名」和「文档里指向这些名字的链接」
对起来。命中就报，不管你本机是哪个平台。

  tools/ci/check_cfg_doc_links.py            # 扫全仓
  tools/ci/check_cfg_doc_links.py crates/x   # 只扫某个目录
"""

import os
import re
import sys

# #[cfg(...)] 换行后紧跟 mod 声明；也覆盖 #[cfg_attr] 之外的常见写法
GATED_MOD = re.compile(
    r"^[ \t]*#\[cfg\((?P<cfg>[^\]]+)\)\][ \t]*\r?\n"
    r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?mod[ \t]+(?P<name>[a-z_][a-z0-9_]*)[ \t]*;",
    re.M,
)
# 文档注释里的 [`name`] 或 [`Self::name`] / [`crate::x::name`]
DOC_LINK = re.compile(r"\[`([A-Za-z_][A-Za-z0-9_:]*)`\]")
SKIP_DIRS = {".git", "target", "node_modules", ".workbuddy"}


def gated_mods(text: str) -> set:
    """返回这个文件里被 cfg 门控的 mod 名集合。"""
    return {m.group("name") for m in GATED_MOD.finditer(text)}


def collect_gated(root: str) -> dict:
    """目录 -> 该目录（含 mod.rs）里被 cfg 门控的 mod 名。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".rs"):
                continue
            path = os.path.join(dirpath, name)
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            names = gated_mods(text)
            if names:
                # 记到目录上：mod.rs 里的链接能看见同目录被门控的子模块，
                # 子模块里的链接也能看见自己那份
                out.setdefault(dirpath, set()).update(names)
                out.setdefault(os.path.dirname(path), set()).update(names)
    return out


def check_file(path: str, gated: dict) -> list:
    dirpath = os.path.dirname(path)
    names = gated.get(dirpath, set())
    # 本文件自己声明的门控 mod（如 lib.rs 里的 pub mod x）
    try:
        names |= gated_mods(open(path, encoding="utf-8", errors="replace").read())
    except OSError:
        return []
    if not names:
        return []
    rel = os.path.relpath(path).replace(os.sep, "/")
    hits = []
    text = open(path, encoding="utf-8", errors="replace").read()
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not (stripped.startswith("//!") or stripped.startswith("///")):
            continue
        for m in DOC_LINK.finditer(line):
            target = m.group(1)
            # 只看裸名字与 Self::name / super::name 这种短路径
            leaf = target.rsplit("::", 1)[-1]
            if target.count("::") <= 1 and leaf in names:
                hits.append(
                    f"{rel}:{lineno}: 文档链接指向 cfg 门控的模块 [`{target}`] —— "
                    f"本机支持的 cfg 与 CI 不同就会 unresolved，请改成不带链接的纯文本"
                )
    return hits


def main() -> int:
    roots = sys.argv[1:] or ["."]
    gated = {}
    files = []
    for root in roots:
        sub = collect_gated(root)
        gated.update(sub)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [os.path.join(dirpath, f) for f in filenames if f.endswith(".rs")]
    bad = []
    for path in files:
        bad += check_file(path, gated)
    print(f"扫描了 {len(files)} 个 Rust 文件，{sum(len(v) for v in gated.values())} 个 cfg 门控模块")
    for line in sorted(set(bad)):
        print(line)
    if bad:
        print(f"\n{len(set(bad))} 处文档链接指向 cfg 门控模块", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())