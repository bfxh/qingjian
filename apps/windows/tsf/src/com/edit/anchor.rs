//! 候选窗口的定位锚点：组句范围 / 选区在屏幕上的矩形，拿不到时退到鼠标位置。

use std::mem::ManuallyDrop;

use windows::Win32::Foundation::{POINT, RECT};
use windows::Win32::UI::TextServices::{ITfContext, ITfRange, TF_DEFAULT_SELECTION, TF_SELECTION};
use windows::Win32::UI::WindowsAndMessaging::GetCursorPos;
use windows::core::BOOL;

use qingjian_platform::protocol::ScreenRect;

/// 只看测量结果，失败给 `None`——回退策略（缓存上次有效位置 / 鼠标）由调用方决定（`report_caret`）。
pub(crate) fn measure_anchor(
    context: &ITfContext,
    ec: u32,
    range: &ITfRange,
) -> Option<ScreenRect> {
    range_rect(context, ec, range).map(to_screen)
}

/// 同上：插入点的测量，没选区 / 量不到都是 `None`。
pub(crate) fn measure_caret(context: &ITfContext, ec: u32) -> Option<ScreenRect> {
    selection_range(context, ec).and_then(|range| measure_anchor(context, ec, &range))
}

/// 当前选区的范围；`GetSelection` 移交所有权，由调用方释放。
pub(crate) fn selection_range(context: &ITfContext, ec: u32) -> Option<ITfRange> {
    let mut selection = [TF_SELECTION::default()];
    let mut fetched = 0u32;
    unsafe {
        context
            .GetSelection(ec, TF_DEFAULT_SELECTION, &mut selection, &mut fetched)
            .ok()?;
    }
    if fetched == 0 {
        return None;
    }
    unsafe { ManuallyDrop::take(&mut selection[0].range) }
}

/// 没有可量的范围时的锚点：鼠标处一个零宽、约一行高的矩形。
pub(crate) fn mouse_screen_rect() -> ScreenRect {
    to_screen(mouse_anchor())
}

fn range_rect(context: &ITfContext, ec: u32, range: &ITfRange) -> Option<RECT> {
    let mut rect = RECT::default();
    let mut clipped = BOOL(0);
    let view = unsafe { context.GetActiveView() }.ok()?;
    let status = unsafe { view.GetTextExt(ec, range, &mut rect, &mut clipped) };
    if let Err(error) = status {
        // #167：Firefox 这类应用 GetTextExt 会失败 / 返回退化矩形，这里记下原因，
        // 看日志就能分清是「应用报错」还是「回了全零矩形」，再决定回退策略。
        crate::com::log::log(&format!("候选锚点：GetTextExt 失败 {error}，回退鼠标"));
        return None;
    }
    if rect.right > rect.left || rect.bottom > rect.top {
        Some(rect)
    } else {
        crate::com::log::log(&format!(
            "候选锚点：GetTextExt 退化矩形 ({},{},{},{})，回退鼠标",
            rect.left, rect.top, rect.right, rect.bottom
        ));
        None
    }
}

fn mouse_anchor() -> RECT {
    let mut point = POINT::default();
    let _ = unsafe { GetCursorPos(&mut point) };
    RECT {
        left: point.x,
        top: point.y,
        right: point.x,
        bottom: point.y + 16,
    }
}

fn to_screen(rect: RECT) -> ScreenRect {
    ScreenRect {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
    }
}
