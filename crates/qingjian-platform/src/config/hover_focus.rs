//! 鼠标悬停聚焦输入框的配置（[hover_focus] 分节）。
//!
//! 详见 `docs/design/hover-focus.md`：鼠标移到某 app 置顶窗口的输入框上时，自动把那个输入框设为系统焦点，
//! 用户不用先点一下就能直接打字。本结构只持有配置项与判定；实际的鼠标监听与设焦点由平台壳做。

use serde::{Deserialize, Serialize};

/// 鼠标悬停聚焦输入框（[hover_focus] 分节）：所有 app 通用，仅一个全局开关，disabled_apps 是安全泄压阀。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct HoverFocusConfig {
    /// 总开关：悬停聚焦输入框；关掉整条功能。缺省开。
    pub enabled: bool,

    /// 光标在某输入框上停留多久（毫秒）才聚焦：去抖，避免划过就抢焦点。缺省 150。
    pub throttle_ms: u64,

    /// 密码 / 安全框跳过（与 IS_PRIVATE 对齐，私密路径不碰）。缺省开。
    pub skip_password: bool,

    /// 安全排除名单：这些 app 里不悬停聚焦。条目是 bundle identifier（macOS）/ exe 文件名（Windows）/
    /// fcitx5 program 名（Linux），`*` 结尾按前缀匹配、不区分大小写，复用 [apps] 的匹配。空 = 所有 app 都生效。
    pub disabled_apps: Vec<String>,
}

impl Default for HoverFocusConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            throttle_ms: 150,
            skip_password: true,
            disabled_apps: Vec::new(),
        }
    }
}

impl HoverFocusConfig {
    /// 这个 app 是否在悬停聚焦的排除名单里（命中则不聚焦）。
    pub fn disabled_app(&self, app: &str) -> bool {
        self.disabled_apps
            .iter()
            .any(|pattern| super::apps::matches_app(pattern, app))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_on_and_safe() {
        let c = HoverFocusConfig::default();
        assert!(c.enabled);
        assert_eq!(c.throttle_ms, 150);
        assert!(c.skip_password);
        assert!(c.disabled_apps.is_empty());
    }

    #[test]
    fn disabled_app_reuses_apps_matching() {
        let c: HoverFocusConfig =
            toml::from_str(r#"disabled_apps = ["com.jetbrains.*", "notepad.exe"]"#).unwrap();
        assert!(c.disabled_app("com.jetbrains.idea"));
        assert!(c.disabled_app("COM.JETBRAINS.RUSTROVER"));
        assert!(c.disabled_app("Notepad.exe"));
        assert!(!c.disabled_app("com.apple.TextEdit"));
        assert!(!c.disabled_app(""));
    }

    #[test]
    fn empty_disabled_list_never_excludes() {
        let c = HoverFocusConfig::default();
        assert!(!c.disabled_app("anything"));
    }
}
