//! 显示器工作区与 DPI 查询，候选窗口与状态条共用。

use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::Graphics::Gdi::{
    GetMonitorInfoW, HMONITOR, MONITOR_DEFAULTTONEAREST, MONITOR_DEFAULTTOPRIMARY,
    MONITOR_FROM_FLAGS, MONITORINFO, MonitorFromPoint, MonitorFromWindow,
};
use windows::Win32::UI::HiDpi::{GetDpiForMonitor, MDT_EFFECTIVE_DPI};

/// `point` 所在（最近）显示器的工作区。
pub(super) fn work_area_near(point: POINT) -> RECT {
    work_area(point, MONITOR_DEFAULTTONEAREST)
}

/// 主显示器的工作区。
pub(super) fn primary_work_area() -> RECT {
    work_area(POINT::default(), MONITOR_DEFAULTTOPRIMARY)
}

/// 拿不到时给个大范围，至少别把窗口夹没。
fn work_area(point: POINT, flags: MONITOR_FROM_FLAGS) -> RECT {
    let mut info = MONITORINFO {
        cbSize: core::mem::size_of::<MONITORINFO>() as u32,
        ..Default::default()
    };
    let found = unsafe {
        let monitor = MonitorFromPoint(point, flags);
        GetMonitorInfoW(monitor, &mut info).as_bool()
    };
    if found {
        info.rcWork
    } else {
        RECT {
            left: 0,
            top: 0,
            right: i32::MAX,
            bottom: i32::MAX,
        }
    }
}

/// `point` 所在（最近）显示器的有效 DPI；拿不到返回 0。
pub(super) fn dpi_at(point: POINT) -> u32 {
    dpi_of(unsafe { MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST) })
}

/// 窗口所在（最近）显示器的有效 DPI；拿不到返回 0。
pub(super) fn dpi_at_window(hwnd: HWND) -> u32 {
    dpi_of(unsafe { MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) })
}

fn dpi_of(monitor: HMONITOR) -> u32 {
    let mut x = 0;
    let mut y = 0;
    let ok = unsafe { GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, &mut x, &mut y) }.is_ok();
    if ok && x > 0 { x } else { 0 }
}
