"""上帝对象**欠账台账**：把「不许有上帝对象」从一句口号变成一份可认领、可验收的清单。

为什么要有它：棘轮门（god_gate.py）只保证「不许变胖」，管不住「历史上就这么胖」——存量
超标会一直躺着。台账做两件事：
  1. 把存量欠账**列出来、排好序**，谁改到谁认领（`docs/review/god-debt.md`）；
  2. `--check` 把台账与基线对账：**手改台账数字 = 红**（数字必须与 `god-baseline.json`
     算出来的一致），而基线本身被棘轮锁着 ⇒ 想让数字变小只能真的去拆。

判据（与 `god_gate.py` 同一份 `god.gate.json`）：
  欠账 = Σ max(0, 指标 - 阈)；指标取**基线值**（基线是承诺值，棘轮只准减），不是当前扫描值。

用法：
  python -X utf8 scripts/gates/god_debt.py --write     # 重写台账（改完基线/拆完一块后跑）
  python -X utf8 scripts/gates/god_debt.py --check     # 门：台账与基线对账（CI / pre-commit）
  python -X utf8 scripts/gates/god_debt.py --touched origin/main   # 我改的文件里哪些还在欠账
退出码：0 = 通过；1 = 对账失败；2 = 配置/IO 错。
"""
import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
LEDGER = ROOT / "docs" / "review" / "god-debt.md"
TOP_N = 40
TOTAL_MARK = "<!-- debt-total: "
KEYS = (("file_lines", "文件行数"), ("max_fn_lines", "最长函数行数"), ("max_type_members", "最大类型成员数"))


def load_gate():
    spec = importlib.util.spec_from_file_location("god_gate_for_debt", ROOT / "scripts" / "gates" / "god_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def debt_of(entry: dict, cfg: dict) -> dict:
    """单文件欠账：{key: 超阈多少}，以及总欠（三项加权：行数 1 / 函数 3 / 成员 2）。"""
    lim = {"file_lines": cfg["max_file_lines"], "max_fn_lines": cfg["max_fn_lines"],
           "max_type_members": cfg["max_type_members"]}
    w = {"file_lines": 1, "max_fn_lines": 3, "max_type_members": 2}
    out, total = {}, 0
    for k, _cn in KEYS:
        d = max(0, entry.get(k, 0) - lim[k])
        if d:
            out[k] = d
            total += d * w[k]
    return {"parts": out, "score": total}


def compute(base: dict, cfg: dict):
    rows, total = [], 0
    for rel, entry in base.items():
        d = debt_of(entry, cfg)
        if d["score"]:
            rows.append((rel, entry, d))
            total += d["score"]
    rows.sort(key=lambda r: -r[2]["score"])
    return rows, total


def render(rows, total, cfg: dict, scanned: int) -> str:
    lim = {"file_lines": cfg["max_file_lines"], "max_fn_lines": cfg["max_fn_lines"],
           "max_type_members": cfg["max_type_members"]}
    cn = dict(KEYS)
    out = [
        "# 上帝对象欠账台账",
        "",
        "由 `scripts/gates/god_debt.py --write` 生成，**不要手改数字**——`--check` 会拿它与 "
        "`god-baseline.json` 对账，改了就红（想让数字变小只能真的去拆）。",
        "",
        f"{TOTAL_MARK}{total} -->",
        "",
        f"- 阈值：文件 ≤ {lim['file_lines']} 行 / 最长函数 ≤ {lim['max_fn_lines']} 行 / 最大类型 ≤ {lim['max_type_members']} 成员（同 `scripts/gates/god.gate.json`）",
        f"- 欠账文件 {len(rows)} 个，总欠账 {total}（加权：行数×1 + 函数×3 + 成员×2——函数最难读，权重最高）",
        f"- 基线在册 {scanned} 个文件；棘轮（god_gate）保证每项只准减 ⇒ 总欠账只准减",
        "",
        "## 认领与清零",
        "",
        "拆一块就在 `.agents/claims/<agent>.json` 里认领对应文件（避免几个智能体同时动一处），"
        "拆完跑 `python -X utf8 scripts/gates/gate.py --write` 重记基线，再跑 `--write` 更新本页。",
        "三项硬阈（`god.gate.json` 的 `*_hard_threshold`）**全部翻 true 之后，欠账即清零**。",
        "",
        "| # | 文件 | 欠账 | 明细 | 认领 |",
        "| - | --- | --- | --- | --- |",
    ]
    for i, (rel, entry, d) in enumerate(rows[:TOP_N], 1):
        detail = "、".join(f"{cn[k]} {entry.get(k, 0)}→≤{lim[k]}（超 {v}）" for k, v in d["parts"].items())
        out.append(f"| {i} | `{rel}` | {d['score']} | {detail} |  |")
    if len(rows) > TOP_N:
        out.append("")
        out.append(f"（另有 {len(rows) - TOP_N} 个欠账文件未列出，跑 `--write` 前的完整清单见命令输出）")
    return "\n".join(out) + "\n"


def recorded_total(text: str):
    i = text.find(TOTAL_MARK)
    if i < 0:
        return None
    j = text.find(" -->", i)
    if j < 0:
        return None
    try:
        return int(text[i + len(TOTAL_MARK):j])
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--touched", metavar="REF", default=None,
                    help="列出：相对该 ref 改过的文件里，哪些还在欠账清单上（碰了就得顺手减）")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args()

    gg = load_gate()
    root = pathlib.Path(a.root).resolve()
    cfg = gg.load_cfg(root, str(ROOT / "scripts" / "gates" / "god.gate.json"))
    bpath = root / cfg["baseline"]
    base = gg.load_baseline(bpath)
    if not base:
        print(f"GOD-DEBT FAIL 基线 {bpath.name} 不存在——先跑 `god_gate.py --write-baseline`")
        return 2
    rows, total = compute(base, cfg)

    if a.touched:
        cp = subprocess.run(["git", "diff", "--name-only", a.touched], cwd=str(root),
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", shell=False)
        changed = {p.strip() for p in cp.stdout.splitlines() if p.strip()}
        hit = [(r, e, d) for r, e, d in rows if r in changed]
        for rel, _e, d in hit:
            print(f"  ⚠ 改了欠账文件 {rel}（欠 {d['score']}）——碰了就顺手减一点，别让它更胖")
        print(f"GOD-DEBT TOUCHED 改了 {len(changed)} 个文件，其中 {len(hit)} 个在欠账清单上"
              f"（提示，不判红；判红的是 god_gate 的棘轮：指标涨了就红）")
        return 0

    if a.write:
        payload = render(rows, total, cfg, len(base))
        tmp = LEDGER.with_suffix(LEDGER.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        import os
        os.replace(tmp, LEDGER)
        print(f"已写台账 {LEDGER.relative_to(root)}：欠账 {len(rows)} 个文件 / 总欠 {total}")
        for rel, _e, d in rows[:10]:
            print(f"  {d['score']:5d}  {rel}")
        return 0

    if not LEDGER.is_file():
        print(f"GOD-DEBT FAIL 台账 {LEDGER.name} 不存在——跑 `--write` 生成")
        return 1
    text = LEDGER.read_text(encoding="utf-8")
    rec = recorded_total(text)
    if rec is None:
        print(f"GOD-DEBT FAIL 台账里找不到 `{TOTAL_MARK}<数> -->` 标记（被手改或格式坏了）")
        return 1
    if rec != total:
        print(f"GOD-DEBT FAIL 台账记 {rec}、基线算出 {total} —— 台账不许手改；"
              f"若刚拆过，跑 `python -X utf8 scripts/gates/god_debt.py --write` 更新")
        return 1
    print(f"GOD-DEBT OK 台账与基线一致（欠账 {len(rows)} 个文件 / 总欠 {total}，只准减）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
