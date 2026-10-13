#!/usr/bin/env python3
"""校验 CHANGELOG.md 的发版格式。

发版流程（release.yml 的 prepare 步骤）靠 CHANGELOG 的标题取版本说明、靠「网盘：」行取官网
下载页的镜像链接，格式错了会直接卡在发版流程里。但 releases_json.py 只在推 v* 标签时才被调用
（release.yml 的 Create draft release 那一步），PR 阶段没有任何检查碰它——标题写错要等标签推了
才发现，而那时候版本已经在发了。

所以这里把「跟格式有关」的部分单独拎出来，在 PR 阶段就能验，纯离线、不碰网络。

判据（HEADING / CHANNELS）**直接从 tools/release/releases_json.py 导入**，不在这边复制一份：
曾经是各写一遍、只靠注释说「改那边记得同步这里」，那种约定迟早会漂移——改了发版那边的正则
而忘了这边，这道门禁就按旧规则放行，比没有门禁更糟（看着绿、实际没验）。

  tools/ci/check_changelog.py            # 校验 CHANGELOG.md
  tools/ci/check_changelog.py path.md    # 校验别的文件
"""

import importlib.util
import os
import re
import sys
from pathlib import Path

# 发版脚本在 tools/release/ 下，按本文件位置推过去；它带 `if __name__ == "__main__"` 守卫，
# 导入不会触发 argparse 与网络访问。
_RELEASE_SCRIPT = Path(__file__).resolve().parent.parent / "release" / "releases_json.py"


def _load_release_module():
    spec = importlib.util.spec_from_file_location("qingjian_releases_json", _RELEASE_SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - 路径错就是部署错了
        raise SystemExit(f"找不到发版脚本 {_RELEASE_SCRIPT}，无法借用它的判据")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_releases = _load_release_module()
# 单一来源：正则与渠道枚举都以发版脚本为准
HEADING = _releases.HEADING
CHANNELS = _releases.CHANNELS

MIRROR_LINE = re.compile(r"^网盘[：:]")
MIRROR_LINK = re.compile(r"\[(?P<name>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)")
ITEM = re.compile(r"^- ")


def check(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    bad = []
    entries = []          # (lineno, version, date, channel)
    mirror_line_no = None
    seen_in_mirror = []

    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip()

        if line.startswith("## "):
            m = HEADING.match(line)
            if not m:
                bad.append(
                    f"{lineno}: 版本标题格式不对，应为「## 版本 · YYYY-MM-DD/未发布 · 渠道」：{line}"
                )
            else:
                if m["channel"] not in CHANNELS:
                    bad.append(
                        f"{lineno}: 渠道只能是 {' / '.join(CHANNELS)}，写的是 {m['channel']}"
                    )
                if m["date"] != "未发布":
                    entries.append((lineno, m["version"], m["date"], m["channel"]))

        elif MIRROR_LINE.match(line):
            # 网盘行必须带至少一个 http(s) 链接，否则官网那一行的按钮是空的
            if not MIRROR_LINK.search(line):
                bad.append(f"{lineno}: 网盘行没有 [名称](链接) 形式的链接：{line}")
            mirror_line_no = lineno
            seen_in_mirror = [m.start() for m in MIRROR_LINK.finditer(line)]

        elif mirror_line_no is not None and ITEM.match(line):
            # 「网盘：」那行之后、下一个标题之前，正文条目不该再出现链接（镜像只走网盘行）
            if MIRROR_LINK.search(line):
                bad.append(
                    f"{lineno}: 更新条目里的链接只应出现在「网盘：」行，本行又出现了一个：{line}"
                )
            mirror_line_no = None

    if not entries:
        bad.append("一个已发布版本都没有（标题带日期的），发版时取不到任何说明")
    else:
        seen = {}
        for lineno, version, _date, _ch in entries:
            if version in seen:
                bad.append(f"{lineno}: 版本 {version} 重复（前面在第 {seen[version]} 行）")
            seen[version] = lineno

    return bad


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "CHANGELOG.md"
    if not os.path.isfile(path):
        print(f"找不到 {path}", file=sys.stderr)
        return 1
    bad = check(path)
    if bad:
        for line in bad:
            print(line)
        print(f"\n{len(bad)} 处发版格式问题", file=sys.stderr)
        return 1
    print(f"{path} 的发版格式没问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())