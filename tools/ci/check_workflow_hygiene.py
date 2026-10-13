#!/usr/bin/env python3
"""校验仓库自己的 CI 工作流有没有踩那几条「写在文件头注释里、但没人验」的规矩。

ci.yml 第一句就写着「actions 一律钉到 commit」「cargo 全加 --locked」。这两条靠人记，
迟早有人加一行 `uses: actions/checkout@v4` 或者漏掉 `--locked` 就悄悄退化：
钉 tag 的 action 可以被强推改写（换成任意代码就在你仓库里跑），漏了 `--locked` 则
Cargo.lock 没了约束、CI 用的依赖树和发版用的可能不是一份。这类问题不报错、只是变弱，
所以要么逐个 review 抓住，要么让脚本每次都扫。

现在查这四条，都是纯静态、离线、不需要网络：

  1. `uses:` 钉到 40 位 commit 而不是 tag / 分支；
  2. 每个 `actions/checkout` 都带 `persist-credentials: false`（PR 来自 fork 时 token 不该留在磁盘上）；
  3. 所有 cargo 子命令都带 `--locked`；
  4. 每个 job 都有 `timeout-minutes`（否则卡死的 job 挂到默认 6 小时，占着并发额度）。

不查 `concurrency` / `permissions`：那两个 GitHub 已经给了安全默认值（前者无、
后者按仓库设置），补上是加分不是必需，缺了也不会变弱。

  tools/ci/check_workflow_hygiene.py            # 扫 .github/workflows/
  tools/ci/check_workflow_hygiene.py path.yml   # 扫指定文件
"""

import re
import sys
from pathlib import Path

# uses: owner/repo@<ref>[/path]。带路径的子 action（owner/repo/.github/actions/x@ref）也认。
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA = re.compile(r"^[0-9a-f]{40}$")
CARGO = re.compile(r"\bcargo\s+(build|check|clippy|test|doc|run|install|update|fetch|tree|metadata)\b")
# 这些子命令不带 --locked 是合理的：install 装的是工具本身（#555 的 cargo-machete 就钉了版本），
# update/fetch/metadata 不产出构建。放行它们，免得门禁逼着人写无意义的 --locked。
LOCK_EXEMPT = {"install", "update", "fetch", "metadata"}

JOB = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
TOP = re.compile(r"^([A-Za-z0-9_-]+):\s*(#.*)?$")


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def job_lines(lines: list) -> list:
    """`jobs:` 块里那些二级键的行号。`on:` 下的 push / pull_request / schedule 同为二级键，
    但它们是触发器不是 job——按缩进分不出来，得看顶层块名。"""
    inside = False
    out = []
    for i, line in enumerate(lines):
        top = TOP.match(line)
        if top:
            inside = top.group(1) == "jobs"
            continue
        if inside and JOB.match(line):
            out.append(i)
    return out


def strip_comment(line: str) -> str:
    """去掉行尾注释，但别动引号里的 # （少见，保守处理）。"""
    out, in_single, in_double = [], False, False
    for ch in line:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).rstrip()


def check_file(path: Path) -> list:
    problems = []
    lines = path.read_text(encoding="utf-8").splitlines()

    # 规则 4：job 集合与各自的 timeout
    jobs = job_lines(lines)
    for n, i in enumerate(jobs):
        name = JOB.match(lines[i]).group(1)
        end = jobs[n + 1] if n + 1 < len(jobs) else len(lines)
        if "timeout-minutes" not in "\n".join(lines[i:end]):
            problems.append((i + 1, f"job `{name}` 没有 timeout-minutes（卡住时默认挂 6 小时）"))

    for i, raw in enumerate(lines, start=1):
        line = strip_comment(raw)
        if not line.strip():
            continue

        m = USES.match(line)
        if m:
            ref = m.group(1)
            if "@" not in ref:
                problems.append((i, f"uses `{ref}` 没有指定 ref"))
            elif not SHA.match(ref.rsplit("@", 1)[1]):
                problems.append((i, f"uses `{ref}` 钉的不是 40 位 commit（tag 可被强推改写）"))
            # 规则 2 只管 checkout
            if "actions/checkout" in ref and "persist-credentials: false" not in raw:
                block = "\n".join(lines[i - 1 : i + 6])
                if "persist-credentials: false" not in block:
                    problems.append((i, "actions/checkout 没有 persist-credentials: false"))
            continue

        m = CARGO.search(line)
        if m and "--locked" not in line and m.group(1) not in LOCK_EXEMPT:
            problems.append((i, f"`cargo {m.group(1)}` 没有 --locked（Cargo.lock 就没约束住依赖树）"))
    return problems


def main(argv: list) -> int:
    if len(argv) > 1:
        targets = [Path(a) for a in argv[1:]]
    else:
        root = Path(__file__).resolve().parent.parent.parent
        targets = sorted((root / ".github" / "workflows").glob("*.yml"))
        targets += sorted((root / ".github" / "workflows").glob("*.yaml"))
    if not targets:
        print("没有可检查的 workflow 文件", file=sys.stderr)
        return 2
    for path in targets:
        if not path.is_file():
            print(f"{path} 不是文件（这个脚本收 .yml 文件，不收目录）", file=sys.stderr)
            return 2

    failed = False
    for path in targets:
        problems = check_file(path)
        rel = path.as_posix()
        for line, msg in problems:
            failed = True
            print(f"{rel}:{line}: {msg}")
    if failed:
        print("\n见 .github/workflows/ci.yml 顶部「actions 一律钉到 commit，cargo 全加 --locked」。")
        return 1
    print(f"workflow 卫生检查通过（{len(targets)} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
