//! 悬停聚焦输入框（step②，Windows 主战场）：鼠标停在别的 app 置顶窗口的输入框上，
//! 不点就把系统键盘焦点设过去，这样能直接打字（详见 `docs/design/hover-focus.md`）。
//!
//! 设计语义：IME 只「借」系统焦点，**不主动组句**。所有 app 通用，仅 `[hover_focus]` 一个总开关，
//! 个别 app 想关用 `disabled_apps`（exe 文件名，`*` 前缀匹配）。密码框跳过（对齐 `IS_PRIVATE`）。
//!
//! 实现：独立后台线程轮询光标位置，用 UI Automation 找光标下的可编辑控件，去抖后跨进程 `SetFocus`。
//! 配置按文件周期热重载，无需重开进程。本模块仅 Windows 编译进 Server。

use std::path::Path;
use std::thread;
use std::time::{Duration, Instant};

use qingjian_platform::Config;
use qingjian_platform::HoverFocusConfig;

use windows::Win32::Foundation::{HWND, POINT};
use windows::Win32::System::Com::{
    CLSCTX_ALL, COINIT_MULTITHREADED, CoCreateInstance, CoInitializeEx,
};
use windows::Win32::System::Threading::{
    GetCurrentProcessId, OpenProcess, PROCESS_NAME_FORMAT, PROCESS_QUERY_LIMITED_INFORMATION,
    QueryFullProcessImageNameW,
};
use windows::Win32::UI::Accessibility::{
    CUIAutomation, IUIAutomation, UIA_CONTROLTYPE_ID, UIA_ComboBoxControlTypeId,
    UIA_DocumentControlTypeId, UIA_EditControlTypeId, UIA_TextControlTypeId,
};
use windows::Win32::UI::WindowsAndMessaging::{GetCursorPos, GetForegroundWindow};
use windows::core::PWSTR;

/// 轮询节拍：比默认去抖（150ms）细，保证「停稳才动、划过不抢」。
const POLL: Duration = Duration::from_millis(60);
/// 配置热重载间隔：文件改了最多 1 秒感知。
const RELOAD_EVERY: Duration = Duration::from_secs(1);

/// 控件类型是不是「可输入」（编辑框 / 富文本文档 / 文本框 / 组合框的可编辑部分）。
pub(crate) fn is_editable(control_type: UIA_CONTROLTYPE_ID) -> bool {
    control_type == UIA_EditControlTypeId
        || control_type == UIA_DocumentControlTypeId
        || control_type == UIA_TextControlTypeId
        || control_type == UIA_ComboBoxControlTypeId
}

/// 起悬停聚焦后台线程（detached，随进程存活）。`path` 用于热重载，`initial` 是启动时的配置。
pub fn spawn(path: Option<std::path::PathBuf>, initial: HoverFocusConfig) {
    thread::Builder::new()
        .name("qingjian-hover-focus".to_owned())
        .spawn(move || run(path, initial))
        .ok();
}

fn run(path: Option<std::path::PathBuf>, initial: HoverFocusConfig) {
    // UI Automation 是 COM 对象，线程要先进套间。已初始化（返回错误）忽略即可。
    let _ = unsafe {
        CoInitializeEx(
            Some(std::ptr::null::<std::ffi::c_void>()),
            COINIT_MULTITHREADED,
        )
    };
    let uia: IUIAutomation = match unsafe { CoCreateInstance(&CUIAutomation, None, CLSCTX_ALL) } {
        Ok(uia) => uia,
        Err(error) => {
            tracing::error!(%error, "UI Automation 初始化失败，悬停聚焦不启用");
            return;
        }
    };

    let my_pid = unsafe { GetCurrentProcessId() };
    let mut cfg = initial;
    let mut last_reload = Instant::now();
    // 去抖状态：记录当前稳定停留的控件句柄，以及从何时开始稳定。
    let mut stayed_hwnd: Option<HWND> = None;
    let mut stable_since: Option<Instant> = None;

    loop {
        thread::sleep(POLL);

        if last_reload.elapsed() >= RELOAD_EVERY {
            if let Some(path) = &path
                && let Ok(loaded) = Config::load(path)
            {
                cfg = loaded.hover_focus;
            }
            last_reload = Instant::now();
        }

        // 总开关关了：清空去抖状态，什么都不做。
        if !cfg.enabled {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }

        let mut point = POINT::default();
        if unsafe { GetCursorPos(&mut point) }.is_err() {
            continue;
        }

        // 只处理前台窗口；后台 app 不抢焦点。
        let foreground = unsafe { GetForegroundWindow() };
        if foreground.is_invalid() {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }

        // 不碰自己进程的窗口（候选框 / 状态条悬停不会偷走焦点）。
        let fg_pid = window_pid(foreground);
        if fg_pid == my_pid {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }

        // 安全泄压阀：该 app 在 disabled_apps 里就跳过。
        if let Some(exe) = exe_name(fg_pid)
            && cfg.disabled_app(&exe)
        {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }

        // 光标下的可编辑控件；取不到 / 不是可编辑 / 密码框 / 不可聚焦 / 已有焦点 → 不动。
        let element = match unsafe { uia.ElementFromPoint(point) } {
            Ok(element) => element,
            Err(_) => {
                stayed_hwnd = None;
                stable_since = None;
                continue;
            }
        };
        if unsafe { element.CurrentIsPassword() }
            .map(|b| b.as_bool())
            .unwrap_or(false)
        {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }
        let control_type = unsafe { element.CurrentControlType() }.unwrap_or(UIA_CONTROLTYPE_ID(0));
        if !is_editable(control_type) {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }
        if !unsafe { element.CurrentIsKeyboardFocusable() }
            .map(|b| b.as_bool())
            .unwrap_or(false)
        {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }
        // 已经持有焦点就不用再设（避免每拍重复 SetFocus）。
        if unsafe { element.CurrentHasKeyboardFocus() }
            .map(|b| b.as_bool())
            .unwrap_or(false)
        {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }
        let hwnd = match unsafe { element.CurrentNativeWindowHandle() } {
            Ok(hwnd) => hwnd,
            Err(_) => {
                stayed_hwnd = None;
                stable_since = None;
                continue;
            }
        };
        if hwnd.is_invalid() {
            stayed_hwnd = None;
            stable_since = None;
            continue;
        }

        // 去抖：同一控件稳定停留 throttle_ms 才设焦点，划过不抢。
        match stayed_hwnd {
            Some(prev) if prev == hwnd => {
                if stable_since.is_none() {
                    stable_since = Some(Instant::now());
                }
            }
            _ => {
                stayed_hwnd = Some(hwnd);
                stable_since = Some(Instant::now());
            }
        }
        if let Some(since) = stable_since
            && since.elapsed() >= Duration::from_millis(cfg.throttle_ms)
            && unsafe { element.SetFocus() }.is_ok()
        {
            // 设成功：清空停留，必须离开再回来才会再次聚焦（已有焦点那分支也会拦重入）。
            stayed_hwnd = None;
            stable_since = None;
        }
    }
}

/// 窗口所属进程 id（`GetWindowThreadProcessId` 的进程出参）。
fn window_pid(hwnd: HWND) -> u32 {
    let mut pid = 0u32;
    unsafe {
        windows::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId(hwnd, Some(&mut pid));
    }
    pid
}

/// 进程 id → exe 文件名（小写，用于 `disabled_apps` 匹配）。取不到返回 `None`，不当成禁用。
fn exe_name(pid: u32) -> Option<String> {
    if pid == 0 {
        return None;
    }
    let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) }.ok()?;
    let mut buf = [0u16; 1024];
    let mut size = buf.len() as u32;
    if unsafe {
        QueryFullProcessImageNameW(
            handle,
            PROCESS_NAME_FORMAT(0),
            PWSTR(buf.as_mut_ptr()),
            &mut size,
        )
    }
    .is_err()
    {
        return None;
    }
    let path = String::from_utf16_lossy(&buf[..size as usize]);
    Path::new(&path)
        .file_name()
        .map(|name| name.to_string_lossy().to_ascii_lowercase())
}

#[cfg(test)]
mod tests {
    use super::is_editable;
    use windows::Win32::UI::Accessibility::{
        UIA_ButtonControlTypeId, UIA_EditControlTypeId, UIA_TextControlTypeId,
    };

    #[test]
    fn editable_controls_are_recognised() {
        assert!(is_editable(UIA_EditControlTypeId));
        assert!(is_editable(UIA_TextControlTypeId));
        assert!(!is_editable(UIA_ButtonControlTypeId));
    }
}
