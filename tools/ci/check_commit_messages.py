#!/usr/bin/env python3
"""校验本 PR 的提交信息首行，规则与 `.githooks/commit-msg` 一致。

钩子只对**有本地仓库、并且记得 `git config core.hooksPath .githooks`** 的人生效。
绕过它的路径至少有两条：GitHub 网页上直接提交、以及合并提交（`git merge` 的默认信息）。
那些路径里攒下格式不合格的提交，等到 `docs/contributing.md` 说的「按 Conventional Commits
读历史」时就不好按 `type(scope)` 过滤了——CHANGELOG 与发版脚本都靠这个前缀。

判据从钩子抄过来，不在这里另立一套：类型集合、范围的正则、还原/fixup 的放行条件
三处都必须与 `.githooks/commit-msg` 一致。两边各写一遍、只靠注释说「改那边记得同步这边」，
那种约定迟早会漂移——改了钩子而忘了这边，这道门禁就按旧规则放行，比没有门禁更糟。

  tools/ci/check_commit_messages.py                 # 比 origin/main..HEAD
  tools/ci/check_commit_messages.py main HEAD       # 显式给范围
  tools/ci/check_commit_messages.py -                # 从 stdin 读一行行首行（给 pre-push 之类用）

自检：`python3 tools/ci/check_commit_messages.py -` 喂上面十种情形那组输入，
输出应恰好是「GitHub 的测试合并放行、本地 Merge branch 拦掉」这样。
"""

import re
import subprocess
import sys

TYPES = r"feat|fix|docs|refactor|perf|test|build|ci|chore|style|revert"
# 与 .githooks/commit-msg 同一条正则：类型(范围)?!: 说明
SUBJECT = re.compile(rf"^({TYPES})(\([a-z0-9._/-]+\))?!?: \S")
# 还原、fixup / squash / amend 是工具自动生成的信息，不要求人写得好看
AUTO = re.compile(r"^(Revert|fixup!|squash!|amend!)")
# GitHub 为 PR 建的**测试合并提交**：`Merge <40位> into <40位>`。它不是任何人写的提交信息，
# 是 GitHub 自己在 refs/pull/N/merge 上造的合并点（CI  checkout 的就是它）。
# 实测：门禁接进来的第一轮就死在这条上，#555 与 #598 都被它挡住。
#
# 放行要**精确**：只放行这一种形状，不能顺手放行所有 `Merge ` 开头——本地
# `git merge`（不打 -m）的默认信息是 `Merge branch 'x'`，.githooks/commit-msg
# 明确要拦那种（「合并提交也要合格式」），这里跟着一起拦才对。
GITHUB_TEST_MERGE = re.compile(
    r"^Merge [0-9a-f]{40}( into [0-9a-f]{40})?$"
)

TYPES_HELP = " / ".join(TYPES.split("|"))


def subjects(spec: str) -> list:
    out = subprocess.run(
        ["git", "log", "--format=%H%x00%s", spec],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if out.returncode != 0:
        raise SystemExit(f"git log {spec} 失败：{out.stderr.strip()}")
    rows = []
    for line in out.stdout.splitlines():
        if "\0" in line:
            sha, subject = line.split("\0", 1)
            rows.append((sha, subject))
    return rows


def check(rows: list) -> list:
    problems = []
    for sha, subject in rows:
        if (
            AUTO.match(subject)
            or GITHUB_TEST_MERGE.match(subject)
            or SUBJECT.match(subject)
        ):
            continue
        problems.append((sha[:9], subject))
    return problems


def main(argv: list) -> int:
    args = argv[1:]
    if args == ["-"]:
        rows = [("", line) for line in sys.stdin.read().splitlines() if line.strip()]
    else:
        spec = "..".join(args) if args else "origin/main..HEAD"
        rows = subjects(spec)
        if not rows:
            print(f"{spec} 之间没有提交，跳过")
            return 0

    problems = check(rows)
    if problems:
        for sha, subject in problems:
            print(f"提交信息首行不合格：{sha} {subject}")
        print()
        print("提交信息第一行要是「<类型>(<范围>): <说明>」，例如 fix(core): 修自绘输入框吞数字")
        print(f"  类型：{TYPES_HELP}")
        print("  范围：小写，crate 或壳的名字（core / platform / render / macos / windows / tsf / cli / docs / ci …），可省略")
        print("  约定见 docs/contributing.md「提交信息」；判据与 .githooks/commit-msg 一致")
        return 1
    print(f"提交信息检查通过（{len(rows)} 个提交）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
