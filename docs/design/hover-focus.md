# 鼠标悬停置顶窗口自动聚焦输入框

需求来源：用户希望输入法在「鼠标移到某个 app 的置顶窗口上」时，默认就能直接打字——输入法自动把光标下的输入框设为系统焦点，之后照常输入即可，不必先点一下输入框。该功能全局生效、可关闭。

本文是设计来源：要做什么、为什么、各平台能力差异与可行性、配置、分层落点、验证方式。实现按 `docs/plan/todo.md` 排期，且遵守「一 PR 一功能、一平台一个 PR」。

## 术语

| 词 | 意思 |
|---|---|
| 置顶窗口 | 光标位置最上层、可见的窗口（鼠标能压到的那个，z-order 最前） |
| 输入框 | 窗口里可键盘输入文本的控件：Win 的 Edit / Document 类、mac 的 AXTextField / AXTextArea / AXComboBox |
| 悬停聚焦 | 鼠标移到输入框上时，用平台 API 把该控件设为系统焦点（不是 IME 自己组句） |
| 前台窗口 | 当前激活、最前面的 app 窗口；置顶且鼠标在其上，通常就是它 |

## 语义

### 触发与判定

- 全局监听鼠标移动（Win 用 Server 进程的定时器轮询光标 / 低层鼠标钩子；mac 用 NSEvent 全局监视器），**节流 + 去抖**：光标在某输入框上停留 ≥ `throttle_ms`（缺省 150）才动作，移动中不抢焦点。
- 取光标下的窗口 / 控件：Win `WindowFromPoint` 拿 HWND，再用 UI Automation（`IUIAutomation::ElementFromPoint` / 沿父链找 `ControlType` 为 Edit / Document）定位输入框；mac `AXUIElementCopyElementAtPosition` 拿元素，沿 `AXParent` 找 `AXRole` 为可编辑文本角色。
- 资格判定（全部满足才聚焦）：
  1. 该窗口是**前台窗口**（`GetForegroundWindow` 命中；mac 取激活 app），避免聚焦后台窗口的控件。
  2. 控件确实是**可编辑文本**（非只读、非禁用）。
  3. 不是**密码 / 安全框**（见守卫）。
  4. 不是输入法自身的候选窗 / 设置窗。
  5. 全局开关 `enabled` 为真，且所在 app 不在 `disabled_apps`。

### 动作

- 仅做一件事：**把该输入框设为系统焦点**（Win `IUIAutomationElement::SetFocus`；mac `AXUIElementSetAttributeValue(kAXFocusedAttribute, true)`）。
- **IME 不主动组句、不读输入框内容**：焦点交给系统后，TSF / IMK 照常把按键路由到这个编辑上下文，组句逻辑完全复用现有通路。即「借系统焦点，IME 本色不变」。

### 守卫（避免抢焦点变成打扰）

- **密码 / 安全框跳过**：Win 查 `ES_PASSWORD` 样式或 UI Automation `IsPassword`；mac 查密码标记；与现有 `IS_PRIVATE` / Secure Input 处理对齐，私密路径不碰。
- **已在输入不抢**：当前前台 app 已有焦点落在某文本控件、且用户正在组句 / 输入时，不把焦点挪走（记录「上次聚焦的控件」，仅当目标变化且当前无活动组句才动作）。
- **自身窗口跳过**：输入法的候选窗、状态条、设置窗不处理。
- **去抖 + 仅在控件变化时动作**：同一控件上移动不重复聚焦；先失焦再进入新控件才聚焦。
- **前台约束**：只处理前台窗口，后台窗口的光标越过不聚焦。

## 平台能力差异与可行性（重要）

这是本功能最大的风险点，写在前头：

- **Windows（可行，主战场）**：UI Automation 跨进程 `SetFocus` 编辑控件普遍可用（内部会先确保窗口前台再设焦点）。TSF 收到焦点变更即激活该编辑上下文，IME 自动接管。本地已有 `apps/windows/tsf/src/com/focus.rs` 的焦点跟踪，新逻辑放 **Server 进程**（常驻单例、已有 UI 线程）更合适，DLL 无需改（TSF 被动响应焦点变化）。
- **macOS（受限，需 spike 验证）**：Accessibility **读取**别的 app 元素需要 `AXIsProcessTrusted` 授权（已在用）；但**写** `kAXFocusedAttribute` 把别的 app 的文本框设为焦点，系统出于安全**通常拒绝或忽略**（跨 app 改焦点 / 位置被限制）。即「悬停自动聚焦框」在 macOS 上可能无法按原语义实现。处置：先做一个最小 spike 验证 `AXUIElementSetAttributeValue(kAXFocusedAttribute, true)` 在已授权下对前台 app 文本框是否生效；若被拒，则 macOS 这步降级为「检测 + 提示」或推迟，不阻塞 Windows 落地。
- **Linux / Wayland（不做）**：无全局窗口与输入框查询能力（Wayland 尤其），X11 的 AT-SPI 也未接入；本期不做，留待 Linux 后续阶段。

> 结论：Windows 端可完整实现并真机验证；macOS 端先验证可行性再决定落地形态，设计上不假设 macOS 一定能设焦点。

## 配置

全局开关（所有 app 通用），写在 `qingjian-platform` 的 `Config`，两个壳共用同一份 `config.toml`：

| 键 | 缺省 | 说明 |
|---|---|---|
| `[hover_focus] enabled` | `true` | 总开关：悬停自动聚焦输入框；关掉整条功能 |
| `[hover_focus] throttle_ms` | `150` | 光标在输入框上停留多久才聚焦（去抖，避免划过就抢焦点） |
| `[hover_focus] skip_password` | `true` | 密码 / 安全框跳过（与 IS_PRIVATE 对齐） |
| `[hover_focus] disabled_apps` | `[]` | 安全排除名单（按 bundleIdentifier / 可执行名 / `*` 前缀，复用 `[apps]` 匹配逻辑）；缺省空 = 所有 app 都生效 |

`enabled` 缺省开，满足「默认支持、可关闭」。`disabled_apps` 是安全泄压阀（如游戏、终端全屏），不破坏「所有 app 通用」的语义。

## 分层与落点

本功能**没有 Core 逻辑**（不排序、不组句、不读词库），纯平台壳能力 + 共享配置，符合架构约束：

| 层 | 放什么 |
|---|---|
| `qingjian-platform` | `[hover_focus]` 配置结构（四个键）、`disabled_apps` 的 `[apps]` 式匹配 |
| Windows 壳 | `apps/windows/server`：全局光标轮询 / 低层鼠标钩子、`WindowFromPoint` + UI Automation 定位与 `SetFocus`；与现有焦点跟踪共存 |
| macOS 壳 | `apps/macos`：NSEvent 全局鼠标监视器、`AXUIElementCopyElementAtPosition` 定位、`kAXFocusedAttribute` 设置（受可行性约束） |
| 设置界面 | Windows `apps/windows/settings`（WinUI 3）与 macOS `apps/macos`（偏好设置）各加一个「悬停聚焦输入框」开关，写同一份 `config.toml`；文案一致 |
| `docs/user/` | 设置页新增该开关的说明（用户可感知的行为改动，实现同 PR 内同步） |

平台层不出现排序 / 词库 / 翻译逻辑。

## 测试与评测

- **Windows（主验证）**：本机 `cargo check --target x86_64-pc-windows-gnu`；真机部署（Server + DLL + 设置）后在记事本 / Edge 地址栏 / 终端悬停验证：移到输入框即聚焦、可直接打字；密码框不聚焦；自身候选窗不抢；`enabled=false` 全关；`disabled_apps` 命中跳过；移动中去抖不抢焦点。**修壳行为必须真机验**（contributing「外部 PR」）。
- **macOS**：先 spike 验证跨 app 设焦点是否可行；可行则同 Windows 真机验（TextEdit 等）；不可行则降级方案单独评审。
- **配置单测**：`throttle_ms` / `disabled_apps` 匹配 / 缺省值（platform crate 单测）。
- **单元**：定位函数（HWND / AX → 可编辑控件）用可控桩件测「找到 / 找不到 / 密码框跳过」三态。

## 后续与不做

**平台范围**：Windows 完整实现并真机验；macOS 视 spike 结果定（可行则同做，不可行则降级或推迟）；Linux / Wayland 不做。

**落地分工**（一 PR 一功能、一平台一个；配置单独 PR）：

| 步 | 范围 | 验证 |
|---|---|---|
| 1 | `qingjian-platform`：加 `[hover_focus]` 配置（含 `disabled_apps` 匹配），纯配置无行为 | `cargo test -p qingjian-platform` |
| 2 | `windows`：Server 内悬停聚焦 + 设置页开关 + `docs/user` 同步 | Windows 真机（Server + DLL + 设置） |
| 3 | `macos`：IMK 内悬停聚焦（先 spike）+ 偏好设置页开关 + `docs/user` 同步 | macOS 真机；不可行则降级评审 |

第 1 步是 2 / 3 前置；第 2、3 步互不依赖。

**不做**：自动在后台窗口聚焦；读输入框内容做任何事；Linux / Wayland 支持；把焦点当快捷键用。

## 参考

- `docs/design/architecture.md`：Core 与平台层划分、TSF 焦点路由。
- `docs/design/candidate-ui.md`：候选窗与按键约定（不冲突，本功能不改候选窗）。
- `docs/design/aux-code.md`：配置 `[apps]` 式匹配与「一 PR 一平台」分工的写法范本。
- `apps/windows/tsf/src/com/focus.rs`：现有 TSF 焦点跟踪（新逻辑与其共存，不重复）。
