# 悬停聚焦输入框设计（未实现）

鼠标移到某 app 置顶窗口的输入框上时，自动把那个输入框设为系统键盘焦点，用户不用先点一下就能直接打字。

> **状态：设计稿，仓库里没有实现。** 实现 PR [#247](https://github.com/qingjian-team/qingjian/pull/247)
> （step②，UI Automation 跨进程 SetFocus）已于 2026-09-27 关闭、从未合并，本文提到的
> `apps/windows/server/src/hover_focus.rs` 与 `crates/qingjian-platform/src/config/hover_focus.rs`
> 都**还不存在**。留这份文档是因为守卫链的取舍与 uiAccess 的边界是当时踩出来的结论，
> 将来若重做可以直接用；如果这个方向已经被否掉（输入法不该替用户移动焦点），
> 删掉这份文档就是。

## 语义

- IME **只「借」系统焦点，不主动组句**。悬停聚焦把光标下的可编辑控件设成键盘焦点，之后敲的字照常进那个控件（由应用自己组句，青简不在此时介入）。
- 所有 app 通用，只有一个总开关 `[hover_focus] enabled`；个别 app 想关用 `disabled_apps`（安全泄压阀）。
- 对齐 `IS_PRIVATE`：密码框跳过，私密路径不碰。

## 平台状态

| 平台 | 状态 | 说明 |
|---|---|---|
| Windows | 设计完成，**未实现**（PR #247 已关闭） | 下面是拟实现的守卫链；真机验收清单见 [`hover-focus-acceptance.md`](hover-focus-acceptance.md) |
| macOS | 未做（拟 spike） | 验 Accessibility 跨 app 写 `kAXFocusedAttribute` 设焦点可行性；受限则降级 |
| Linux | 未排期 | 焦点跟踪走 fcitx5 program 名；`disabled_apps` 的匹配逻辑（前缀 `*` + 不区分大小写）可复用 `apps::matches_app`（那一层是现成的，`hover_focus` 专用代码尚未写） |

## 拟实现的守卫链（优先级顺序，Windows）

后台线程以 `POLL = 60ms` 节拍轮询光标位置，每拍按下面顺序判定；任一不满足就清空去抖状态、`continue`，什么都不做：

1. **总开关**：`enabled == false` → 整条功能停摆，线程空转不动作。
2. **仅前台窗口**：先 `GetForegroundWindow()`，无效（foreground 为空）跳过。只处理当前置顶的窗口，后台 app 不抢焦点。
3. **不碰自身进程**：`fg_pid == GetCurrentProcessId()`（候选框 / 状态条悬停不会偷走焦点）。
4. **`disabled_apps` 泄压阀**：取前台进程 exe 名（小写）→ `cfg.disabled_app(exe)`；命中（前缀 `*` 匹配、不区分大小写，复用 `[apps]` 的 `matches_app`）跳过。
5. **光标下有可编辑控件**：`IUIAutomation::ElementFromPoint` → `is_editable(control_type)`（`Edit` / `Document` / `Text` / `ComboBox` 的可编辑部分）；取不到或不是可编辑跳过。
6. **密码框跳过**：`element.CurrentIsPassword()` 为真跳过（对齐 `IS_PRIVATE`）。
7. **可聚焦**：`element.CurrentIsKeyboardFocusable()` 为假跳过。
8. **已持有焦点不重设**：`element.CurrentHasKeyboardFocus()` 为真跳过，避免每拍重复 `SetFocus`。
9. **去抖**：同一控件稳定停留 `≥ throttle_ms` 才 `element.SetFocus()`；划过不抢，停稳才动。设成功清空停留状态——必须离开再回来才会再次聚焦（配合第 8 条拦重入）。

配置按文件周期热重载（`RELOAD_EVERY = 1s`，重新 `Config::load` 覆盖 `cfg`），保存即生效，无需重开进程。

## uiAccess 边界（真机验收前必读）

这是最易踩、CI 测不出的坑。与功能是否实现无关，将来重做时照样适用：

- Server 经 `apps/windows/server/build.rs` 嵌 `uiAccess` manifest，受环境变量 `QINGJIAN_UIACCESS` 控制，**默认 `true`**；设 `0` 关掉（CI 的 windows job、`test-local.ps1`、对外分发的包都用 `0`）。
- **未签名、又没装到 `%ProgramFiles%` 的 exe 带 `uiAccess=true` 会直接起不来**（os error 740）。系统只对「代码签名且装在安全位置（Program Files）」的 exe 授予 uiAccess。
- **uiAccess 的作用**：让候选窗口能 `SetWindowPos(HWND_TOPMOST)` 升进 UIAccess 高 z-band，从而盖过 UWP 宿主（任务栏搜索、设置这类商店应用）。它管的是**候选窗的层级覆盖**，不是 hover 设焦点。
- **与 hover `SetFocus` 的关系**：hover 只对「**已经是前台窗口的子控件**」设焦点（第 2 条先取前台窗口，再 `ElementFromPoint`），不更换顶层前台窗口。给已是前台的窗口的子控件设焦点不受前台锁限制，所以**普通桌面 app（记事本 / VSCode / 资源管理器地址栏）用 `QINGJIAN_UIACCESS=0` 就能完整验收核心效果**。
- 走完整 uiAccess（候选窗在 UWP 宿主上也不被盖）：用 `apps/windows/installer/build.ps1 -Sign`——它会 `uiAccess=1` 重新构建、用 `sign-local.ps1` 造自签证书并装进本机 `LocalMachine` 受信任根、`signtool` 签名，再经 Inno 装到 `%ProgramFiles%`。详见 `apps/windows/installer/README.md`。**`-Sign` 只用于本机真机测，自签证书只有本机信任，不能对外分发**（对外分发用 `=0`，任何机器都能起，代价是候选窗在几个系统界面里可能被盖）。

## 拟新增的配置（`[hover_focus]` 分节）

下列字段**尚不存在**，重做时按此加进 `crates/qingjian-platform/src/config/`：

| 字段 | 缺省 | 含义 |
|---|---|---|
| `enabled` | `true` | 总开关；关掉整条功能 |
| `throttle_ms` | `150` | 光标在输入框上停留多久（毫秒）才聚焦；去抖，划过不抢 |
| `skip_password` | `true` | 密码 / 安全框跳过 |
| `disabled_apps` | `[]` | 安全排除名单：`*` 结尾按前缀匹配、不区分大小写；空 = 所有 app 都生效 |

`disabled_apps` 条目在 Windows 是 exe 文件名（如 `notepad.exe`、`code*`），macOS 是 bundle identifier，Linux 是 fcitx5 program 名；匹配逻辑跨平台复用 `apps::matches_app`。

## 验收

真机验收清单与构建 / 运行步骤见 [`hover-focus-acceptance.md`](hover-focus-acceptance.md)（同样要在实现落地后才能跑）。

