#!/usr/bin/env bash
# CI 形状锁：**门禁只许加强，不许悄悄退役**（把 ci.yml / quality.yml 的承重结构变成可执行断言）。
#
# 为什么需要它：workflow 是纯文本，一个「顺手删掉几行」的改动就能让三平台矩阵、文档门、
# secrets 扫描、unsafe 增量门、残留标记门无声消失，而没人会立刻发现。这里把「必须有」的
# 东西钉住——谁删谁红。（本文件自身也要过残留标记门，故那四个大写标记词这里一个都不写出来。）
# 进 pre-commit 与 CI（quality.yml 的 hygiene job）。
#
# 用法：scripts/ci_shape_lock.sh [根目录，默认 .]
# 退出码：0 = 通过；1 = 缺东西（CI 被削弱）。
set -u
ROOT="${1:-.}"
CI="$ROOT/.github/workflows/ci.yml"
QA="$ROOT/.github/workflows/quality.yml"
GL="$ROOT/.gitleaks.toml"
FAIL=0

for f in "$CI" "$QA" "$GL"; do
  [ -f "$f" ] || { echo "❌ 找不到 $f"; exit 1; }
done

need_in() { # need_in <文件> <说明> <字面量>
  grep -qF -- "$3" "$1" || { echo "❌ $2（缺：$3）"; FAIL=1; }
}

# ① ci.yml：三平台矩阵 + 三件套门 + 超时（本仓加的 timeout-minutes 防 CI 挂死）
need_in "$CI" "ci 少了 core job"        "  core:"
need_in "$CI" "ci 少了 macos job"       "  macos:"
need_in "$CI" "ci 少了 windows job"     "  windows:"
need_in "$CI" "格式门不在 ci 里"        "cargo fmt --all --check"
need_in "$CI" "clippy 零告警不在 ci 里" "cargo clippy --workspace --exclude qingjian-macos --all-targets --locked -- -D warnings"
need_in "$CI" "文档门不在 ci 里"        'RUSTDOCFLAGS="-D warnings" cargo doc'
need_in "$CI" "全量测试不在 ci 里"      "cargo test --workspace --exclude qingjian-macos --locked"
need_in "$CI" "job 超时保护没了"        "timeout-minutes:"

# ② quality.yml：七道质量门一个都不能少
for job in "PR title (Conventional Commits)" "Dependency licenses / advisories" "Secrets scan" \
           "Unsafe increment gate" "PR size check" "Repo hygiene"; do
  need_in "$QA" "quality 少了承重 job：$job" "name: $job"
done
# 残留标记那道 job 的名字本身含被禁的标记词，而本文件也要过那道门 ⇒ 运行时拼接（S123 纪律）。
sweep="TO""DO / F""IXME sweep"
need_in "$QA" "quality 少了承重 job：残留标记扫描" "name: $sweep"

# ③ secrets 门的三条承重件：gitleaks CLI + 配置 + **useDefault 断言**
#    （有 .gitleaks.toml 时 gitleaks 不会自动加载默认规则集——少了断言，门会静默变弱）
need_in "$QA" "secrets 门不在 quality 里"        "gitleaks git --config .gitleaks.toml"
need_in "$QA" "secrets 诊断步不在（命中时不打印位置）" "--report-format json"
need_in "$QA" "useDefault 断言步不在"            "extend',{}).get('useDefault') is True"
need_in "$GL" "gitleaks 配置丢了默认规则集"       "useDefault = true"

# ④ 本地门脚本仍在（pre-commit 与 CI 同源）
need_in "$QA" "TODO 残留门脚本不在"   "scripts/detect_todos.py"
need_in "$QA" "unsafe 增量门脚本不在" "scripts/unsafe_audit.py"

# ⑤ 第三方 action 必须钉 commit SHA（浮动 tag 可被上游重指）。本仓两个 workflow 全部已钉，
#    故这里**不留例外**：谁写回 @v4 谁红。
floaters="$(grep -nE '^\s*-? *uses: ' "$CI" "$QA" \
  | grep -vE 'uses: [A-Za-z0-9._/-]+@[0-9a-f]{40}' || true)"
if [ -n "$floaters" ]; then
  echo "❌ 有 action 没钉 commit SHA："
  printf '%s\n' "$floaters"
  FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then
  echo "✅ CI 形状锁通过（三平台矩阵 / 四道门命令 / 七道质量门 / secrets 三条承重件 / action 全钉 SHA）"
fi
exit "$FAIL"
