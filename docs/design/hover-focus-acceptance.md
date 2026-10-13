# 悬停聚焦输入框 · 真机验收清单（Windows）

> **状态：功能未实现，这张清单现在跑不了。** 实现 PR
> [#247](https://github.com/qingjian-team/qingjian/pull/247) 已于 2026-09-27 关闭、从未合并，
> 下面第 2 节写的 `[hover_focus]` 配置分节在仓库里也不存在（照写会被配置解析忽略，
> 各项会因「功能压根没启动」而全部不通过）。留着是为了将来重做时能直接照勾。

本清单对应 [`hover-focus.md`](hover-focus.md) 的守卫链与 uiAccess 边界，供在 Windows 真机逐条照勾。沙箱无 GUI / IME，无法替跑。

## 0. 前置

- 本机已装过一次青简（有真实词库 / 数据），或 `test-local.ps1` 用 `-InstallDir` 指到一份安装目录。
- 五笔码表已生成（见 `assets/wubi/README.md`，`dict-convert wubi`）；否则译文全空会误判。
- 需要的东西仅本机有：PowerShell 7（`pwsh`）、Rust + mingw（gnu target，见下）、装好的青简。

## 1. 构建 / 运行（默认 `QINGJIAN_UIACCESS=0`，足以验核心）

```powershell
# 仓库根目录
pwsh -File apps\windows\scripts\test-local.ps1
```

脚本做的事：`QINGJIAN_UIACCESS=0` 编 Server + TSF DLL → 停旧 Server → 把 `%ProgramFiles%\Qingjian` robocopy 到 `~\qingjian-devtest`（带真实数据）→ 拷新 Server / DLL / 码表 → 注册 DLL（非管理员只打印 `regsvr32` 命令让你手跑）→ `Start-Process` 起 Server。

坑（脚本注释也有）：
- 编时若报「有进程正加载着 `qingjian_tsf.dll`」写不进去 → `Win+Space` 切到别的输入法（或 Shift 切英文）让 DLL 卸载再重跑。
- 改完配置要**关掉记事本重开**：已在跑的进程攥着旧 DLL，注册新的对它无效。

> 要验 UWP 宿主（任务栏搜索 / 设置）里候选窗不被盖 + 走完整 uiAccess：改用 `apps\windows\installer\build.ps1 -Sign`（自签 + 装 ProgramFiles）。详见 `hover-focus.md` 的「uiAccess 边界」。
> 那一步需要 Windows SDK 的 `signtool` 与 Inno Setup，且只本机可信——**不用于对外分发**。

## 2. 配置（实现落地后才有；保存即热加载，不用重启）

拟新增的 `%APPDATA%\Qingjian\config.toml` 分节：

```toml
[hover_focus]
enabled = true        # 总开关
throttle_ms = 150     # 去抖阈值（毫秒）
skip_password = true  # 密码框跳过
disabled_apps = []    # 如 ["notepad.exe"]、"code*" 前缀匹配
```

日志佐证（可选）：`Get-Content "$env:LOCALAPPDATA\Qingjian\logs\qingjian-server.*.log" -Tail 20`。

## 3. 验收项（逐条打勾）

默认全开状态下：

- [ ] **0. 前置自检**：先确认 `[hover_focus]` 真的被读到了（见第 2 节的日志佐证）。
      这一条在功能未实现时必然不过，别把「没反应」误判成守卫链第 1 条不灵。
- [ ] **1. 基础聚焦**：鼠标移到记事本空白输入框、停 ~150ms，光标自动进入输入框，**不用点一下就能直接打字**。
- [ ] **2. 去抖手感**：快速划过输入框不抢焦点；悬停停稳才动。
- [ ] **3. 调参确认手感**：把 `throttle_ms` 调大到 600 → 划过更明显不抢；调小到 50 → 更敏感。确认 150 是否合适（手感主观，记下结论）。
- [ ] **4. `disabled_apps` 泄压阀**：设 `disabled_apps = ["notepad.exe"]` 后，记事本不再自动聚焦；VSCode / 资源管理器地址栏仍生效。
- [ ] **5. 密码框守卫**：浏览器登录页 / Windows 改密码框，悬停**不抢焦点**。
- [ ] **6. 已聚焦不重设**：控件已有焦点时悬停，不重复 `SetFocus`（无每拍抖动）。
- [ ] **7. 不偷自身窗口**：悬停在青简候选框 / 状态条上，焦点不被偷走。
- [ ] **8. 只前台**：后台 app 的输入框悬停不聚焦。
- [ ] **9. 总开关**：`enabled = false` 后整条功能停摆、线程空转。

## 4. 回表

把 #1 / #3 / #4 / #5 / #6 的实测结果（尤其 `throttle_ms = 150` 手感是否合适）反馈，再决定要不要调默认阈值，然后推进 macOS 壳的 `kAXFocusedAttribute` spike。
