# 多智能体协作协议（本仓同时有多个智能体在开发）

**一句话**：动代码前先认领，认领写在你自己那一个文件里，域不重叠才动手。
机器判据在 `scripts/gates/agent_gate.py`（`gate.py --fast` 与 CI 都跑），人读这一页。

## 为什么

几个智能体并行改同一个仓，最容易出的不是 git 冲突，而是**语义冲突**：各改半个函数、各自
往同一个模块塞 helper，git 能合并，语义不能。靠 `AGENTS.md` 里写一句「请避免冲突」没用——
没人看，也没机器判。所以：认领做成文件，冲突做成红灯。

## 怎么做

1. 起手先建 `.agents/claims/<你的-id>.json`（文件名与 `agent` 字段**必须相同**）：

```json
{
  "agent": "your-agent-id",
  "driver": "谁在驱动（可选）",
  "branch": "ci/your-branch",
  "task": "一句话说清你在干什么",
  "scope": ["crates/qingjian-core/src/engine/**", "docs/notes/crate-notes.md"],
  "opened": "2026-09-25",
  "expires": "2026-09-27"
}
```

2. 动手前设身份（越界检查靠它）：

```bash
export QJ_AGENT_ID=your-agent-id          # 或：git config qingjian.agentId your-agent-id
```

3. 跑 `python -X utf8 scripts/gates/gate.py --fast`，`agent-gate` 绿了再提交。
4. 干完**把你的声明文件删掉**（或续期），别占着域不走。

## 判据（agent_gate.py）

| 编号 | 规则 | 命中 |
| --- | --- | --- |
| A1 | 文件名 stem == `agent`；`agent`/`task`/`scope`/`expires` 必填；`expires` 是 `YYYY-MM-DD` | 红 |
| A2 | 一个智能体只许一份声明 | 红 |
| A3 | 两份**未过期**声明的 scope 有交集（模式级 + 实际文件级） | 红 |
| A4 | 你改的文件落在**别人的**活跃域里 | 红 |
| A5 | 设了 `QJ_AGENT_ID` 却没有对应活跃声明 | 红 |
| — | 你改的文件不在自己的 scope 内 | **提示**（跨模块小改请补 scope 再提交） |

CI 上没有 `QJ_AGENT_ID` ⇒ 跳过 A4/A5（CI 是只读校验，靠 A3 挡域重叠）。
CI 不设身份不会让门静默变绿：A1–A3 照跑。

## 为什么「一智能体一文件」而不是共用一份 JSON

共用一份 `claims.json` 时，两个智能体同时写 = 写冲突，还得引入锁。分成一人一个文件后，
文件名天然互异 ⇒ 不存在写冲突；冲突的判定交给 A3（机器读全部文件后判交集）。

## 与上帝对象门的关系

`docs/review/god-debt.md` 里的每个欠账文件，认领时把路径写进你的 `scope`
（拆大函数会大改那个文件，不认领就会跟别人撞）。拆完跑：

```bash
python -X utf8 scripts/gates/gate.py --write   # 重记三条基线（要 git diff 过目）
python -X utf8 scripts/gates/gate.py --fast
```

## 门禁文件地图

| 文件 | 管什么 |
| --- | --- |
| `scripts/gates/gate.py` | 统一入口（`--fast` / `--only` / `--write`） |
| `scripts/gates/god_gate.py` + `god.gate.json` | 上帝对象：文件/函数/类型规模棘轮 + 分项硬阈 |
| `scripts/gates/god_debt.py` + `docs/review/god-debt.md` | 存量欠账台账（数字不许手改） |
| `scripts/gates/dupe_gate.py` | 雷同代码新增即红（纯 stdlib MinHash） |
| `scripts/gates/agent_gate.py` | 多智能体认领 / 域不重叠 / 不越界（本页） |
| `scripts/gates/gate_selftest.py` | 门禁自检：门不许被悄悄削弱或绕过 |
