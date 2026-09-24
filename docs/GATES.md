# 门禁（结构与协作）

`ci.yml` 管编译与测试，`quality.yml` 管依赖、秘密与仓库卫生，**这一组管结构与协作**：
不许有上帝对象、不许新增雷同代码、多个智能体并行时不许互相踩、门本身不许被悄悄削弱。

移植自 `D:/开发/unified-rx-mcp`（那边是一整套 Python 门禁），按本仓（Rust workspace、多智能体并行）
做了适配：门脚本全部**零依赖、纯 stdlib**，CI 上 `python3` 直接跑，不需要装任何东西。

一条命令：

```bash
python -X utf8 scripts/gates/gate.py --fast     # 快门（pre-commit 同款，秒级，不需 cargo）
python -X utf8 scripts/gates/gate.py            # 全门（含 fmt / clippy / 全量测试；合入前跑）
python -X utf8 scripts/gates/gate.py --list     # 看看都有哪几道
python -X utf8 scripts/gates/gate.py --only god-gate,dupe-gate
python -X utf8 scripts/gates/gate.py --write    # 拆完一块后重记基线（**要 git diff 过目**）
```

## 一、上帝对象门（`god_gate.py` + `god.gate.json`）

**纪律来源**：`docs/contributing.md`「代码组织」——单文件 ≤800 行（目标 500）、一个类型一个文件、
大类型 `impl` 按职责拆子模块。门把那三条从「写给人看」变成「机器判」。

三个指标、每条都有**棘轮**与**硬阈**两档（`god.gate.json` 里分别开关）：

| 指标 | 阈值 | 棘轮 | 硬阈 | 存量 |
| --- | --- | --- | --- | --- |
| `file_lines` 文件行数 | 800 | 只准减 | **开**（`file_hard_threshold: true`） | 存量全绿（最大 738） |
| `max_fn_lines` 最长函数 | 100 | 只准减 | 待开 | 46 个文件欠账，见台账 |
| `max_type_members` 最大类型成员 | 20 | 只准减 | 待开 | 同上 |

- **棘轮**：任何指标超过基线值 ⇒ 红。低于基线 ⇒ 绿，并提示可收紧基线（只准减）。
- **硬阈**：`true` 时**存量超阈也红**（不接受基线祖父化）。三项分开开闸——
  `file_lines` 落地当天就开（存量已全绿）；另两项等 `docs/review/god-debt.md` 的欠账清零后再翻，
  翻转动作由 `gate_selftest.py` 的 S3 锁住：**只许 false→true，不许改回**。
- **拆函数的合法交换**：把长函数拆成 helper 会让文件变长。若 `max_fn_lines` 严格下降、
  且涨幅 ≤10%（或函数降幅 ≥ 文件涨幅），判合法交换并逐条打印；函数没变短就别想涨行数。
- **新文件**：没有基线可依赖，直接对阈值判。
- Rust 用花括号配平启发式（先掩掉字符串/注释/生命周期再配平），输出标注 `H`。

改基线前先看差：`python -X utf8 scripts/gates/god_diff.py`（`--write-baseline` 会一次性重记
所有值 = 放松棘轮，先看差才能分清「纠正测量」与「真变胖」）。

## 二、欠账台账（`god_debt.py` + `docs/review/god-debt.md`）

棘轮只保证「不许变胖」，管不住「历史上就这么胖」。台账把存量欠账列出来、排好序、可认领：

- 欠账 = Σ max(0, 指标 − 阈)，加权 行数×1 + 函数×3 + 成员×2（函数最难读，权重最高）；
- `--check`：台账里的总数必须与 `god-baseline.json` 算出来的一致 ⇒ **手改数字 = 红**，
  想让数字变小只能真的去拆；
- `--touched <ref>`：列出「这次改动碰到的欠账文件」（提示，不判红）——碰了就顺手减一点。

拆一块的流程：先认领 → 拆 → `gate.py --write` → `gate.py --fast` → 提交。

## 三、类型跨度门（`type_span_gate.py`）

**为什么还要单独一道**：`docs/contributing.md` 要求「大类型的 `impl` 按职责拆成子模块」。
拆完之后每个文件都只有一两百行，`god_gate` 的三项指标全绿——但那个**类型本身**可能还是个
庞然大物。按文件量规模**永远**抓不到它，必须按类型名把 `impl` 块聚合起来看。

判据（每个 crate 内按类型名聚合）：

| 指标 | 阈值 | 棘轮 | 硬阈 |
| --- | --- | --- | --- |
| `methods` 该类型所有 impl 的方法总数 | 40 | 只准减 | 待开 |
| `files` 这些 impl 散在几个文件 | 8 | 只准减 | 待开 |

当前最重的一处：`crates/qingjian-core|Engine` —— **207 个方法、散在 16 个文件**。
这是本仓最典型的上帝对象，而它在按文件统计的门里是全绿的。

## 四、架构约束门（`arch_gate.py`）

把 `docs/contributing.md` 那一页「架构约束 / 代码组织」从写给人看变成机器判。
那些规矩每一条都写得很清楚，但没有一条有人或机器在查。

| 编号 | 规则 | 命中 |
| --- | --- | --- |
| R1 | 新 `.rs` 文件缺 `//!` 文件头 | 红（只管新增） |
| R2 | 新文件（非 `mod.rs` / 非测试）顶层类型 > 1 | 红（只管新增） |
| R3 | `use …::*` glob 导入 | 棘轮（`#[cfg(test)]` 与测试文件豁免） |
| R4 | `foo.rs` 与 `foo/` 并列 | 棘轮 |
| R5 | `crates/*` 无条件依赖 `apps/*` 的 crate 或 OS 特有 crate（objc2 / windows / gtk …） | **红（硬）** |
| R6 | 产品代码里的 `dbg!` / `todo!` / `unimplemented!` / `unreachable!` / 裸 `panic!` | 棘轮 |
| R7 | 装饰性分隔注释 `// ====` | 棘轮 |

R5 只查**无条件**的 `[dependencies]` 段：`[target.'cfg(windows)'.dependencies]` 是平台后端
（render 用 DirectWrite 列字族），crate 本身仍跨平台，把条件依赖也算违规会逼人改写成绕过。

R6 为什么单独扫一遍：workspace lints 已经 deny 这些，但 clippy 只跑编得到的 target——
macOS 壳在 Linux runner 上不编、Windows 三件套在 macOS runner 上不编 ⇒ 那部分文件的 `panic!`
谁也抓不到。这里是纯文本扫描，不看能不能编译，正好补上那个**平台盲区**。

## 五、重复代码门（`dupe_gate.py`）

上帝对象门管「单点过大」，这个管「多处雷同」——拆上帝对象时最容易顺手复制出一批雷同的
helper，所以两个门配套。

- 判据：文件对 Jaccard ≥ 0.80（bottom-k MinHash，ng=5 / k=128）即雷同；**基线里没有的新对 ⇒ 红**。
- **与上游的差异（重要）**：上游调用 Rust 侧 `rx-scan.exe` 出指纹，那个 exe 在本仓与 CI 上都没有，
  照抄会以「引擎不可用」把所有人卡死。这里改成**纯 stdlib** 实现（同口径），零依赖。
- 当前基线 9 对，全是 `apps/linux/server` 与 `apps/windows/server` 之间的复制——真欠账，不是误报。
  真要消掉得抽公共 crate，而不是再复制一份。

## 六、多智能体协作门（`agent_gate.py` + `.agents/CLAIMS.md`）

本仓同时有好几个智能体在开发。认领写在你自己那一个文件里（`.agents/claims/<id>.json`），
文件名互不相同 ⇒ 天然没有写冲突；冲突判定交给机器（A3 域重叠）。

| 编号 | 规则 | 命中 |
| --- | --- | --- |
| A1 | 文件名 stem == `agent`；`agent`/`task`/`scope`/`expires` 必填 | 红 |
| A2 | 一个智能体只许一份声明 | 红 |
| A3 | 两份未过期声明的 scope 有交集 | 红 |
| A4 | 改了别人活跃域里的文件 | 红 |
| A5 | 设了 `QJ_AGENT_ID` 却没有对应声明 | 红 |

完整协议、声明模板、文件地图见 [`.agents/CLAIMS.md`](../.agents/CLAIMS.md)。

## 七、门禁自检（`gate_selftest.py`）

门全是仓库里的文本文件——删掉 workflow 一行、调大阈值、把硬阈改回 false、把钩子里的
`--fast` 去掉，都不会让任何测试变红，门却已经没了。**门静默变弱比没有门更危险**（它还挂着绿勾）。

- S1 本地 `gate.py` 的 STEPS 与 `.github/workflows/gates.yml` **双向同源**（少一步即红）；
- S2 `.githooks/pre-commit` 必须调用 `gate.py --fast`；
- S3 `god.gate.json` 相对 HEAD：阈值只许收紧、硬阈只许 false→true、`include` 不许少、`exclude` 不许多；
- S4 `god_gate.py` 的两处本仓适配仍在（上游重抄整文件时最容易抄丢）；
- S5 基线在位且是合法 JSON；
- S6 `.agents/CLAIMS.md` 在位。
- S7 `ci.yml` 的 `gate-shape` 锚在位（两处互盯，见下）。

CI 里额外跑一次**注入自检**：`QJ_GATE_FORCE_FAIL=god-gate` 时门必须红，绿了说明这一步根本没生效。

## 八、接进流水线的地方

| 位置 | 跑什么 |
| --- | --- |
| `.githooks/pre-commit` | `gate.py --fast`（快门，秒级） |
| `.github/workflows/gates.yml` | 五个 job：上帝对象（含类型跨度）/ 架构约束 / 重复代码 / 多智能体协作 / 门禁自检 |
| `ci.yml` 的 `gate-shape` job | **钉子挂在这里**：gates.yml 被整个删掉时它自己不会跑，得由别处盯住 |
| `gate_selftest.py` S1/S2 | 钉住「本地有 CI 没有」「CI 有本地没有」「钩子上没挂快门」三种漂移 |

`unsafe` 与 `todos` 两步在 `gate.py` 里是**条件步**：那两个脚本属另一条 CI 分支的工作，
尚未合进 main ⇒ 脚本不在时显式 `SKIP` 并打印原因（不静默判绿），合入后自动生效。
