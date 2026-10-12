//! `--tune 名=值`：把引擎里几组「拍的」常数换成别的值，回放评测时扫参数用；名字见 [`KEYS`]。

use qingjian_core::Engine;
use qingjian_core::correction::TypoCosts;
use qingjian_core::sentence::{Interpolation, SearchLimits};

/// 可调的参数名。前四个是个人 n-gram 插值，接着六个是敲错代价，最后三个是整句搜索规模
/// （每格候选数 / 简拼格候选数 / 束宽）——那三个原本是编译期常量，只能改代码重建才能试，
/// 而它们对准确率和延迟的影响不比插值参数小。
pub const KEYS: [&str; 14] = [
    "lambda",
    "k",
    "cap",
    "discount",
    "transpose",
    "substitute",
    "extra",
    "missing",
    "typo-cap",
    "correction",
    "correction-transpose",
    "span",
    "abbreviated-span",
    "beam",
];

/// 把一组 `名=值` 应用到引擎；没给的项保持缺省。
pub fn apply(engine: &mut Engine, settings: &[String]) -> Result<(), TuneError> {
    if settings.is_empty() {
        return Ok(());
    }
    let mut interpolation = Interpolation::default();
    let mut costs = TypoCosts::default();
    let mut limits = SearchLimits::DEFAULT;
    for setting in settings {
        let (key, value) = setting
            .split_once('=')
            .ok_or_else(|| TuneError::Syntax(setting.clone()))?;
        let key = key.trim();
        let value = value.trim();
        match key {
            "lambda" => interpolation.lambda = number(value)?,
            "k" => interpolation.confidence_k = number(value)?,
            "cap" => interpolation.max_confidence = number(value)?,
            "discount" => interpolation.trigram_discount = number(value)?,
            "transpose" => costs.transpose = number(value)?,
            "substitute" => costs.substitute = number(value)?,
            "extra" => costs.extra = number(value)?,
            "missing" => costs.missing = number(value)?,
            "typo-cap" => costs.discount_cap = number(value)?,
            "correction" => costs.correction_penalty = number(value)?,
            "correction-transpose" => costs.correction_transpose_discount = number(value)?,
            "span" => limits.span_candidates = count(value)?,
            "abbreviated-span" => limits.abbreviated_span_candidates = count(value)?,
            "beam" => limits.beam_width = count(value)?,
            other => {
                return Err(TuneError::Unknown {
                    name: other.to_owned(),
                });
            }
        }
    }
    tracing::info!(?interpolation, ?costs, ?limits, "参数覆盖");
    engine.set_interpolation(interpolation);
    engine.set_typo_costs(costs);
    engine.set_search_limits(limits);
    Ok(())
}

/// 浮点参数。拒绝 NaN / inf：它们会让排序比较器全部返回 Equal，结果是「静默不排序」而不是报错。
fn number(value: &str) -> Result<f64, TuneError> {
    let parsed: f64 = value
        .parse()
        .map_err(|_| TuneError::Value(value.to_owned()))?;
    if !parsed.is_finite() {
        return Err(TuneError::Value(value.to_owned()));
    }
    Ok(parsed)
}

/// 规模参数：至少为 1。给 0 不会「少算一点」，而是让整句转换直接返回空——
/// 那种配置在评测里表现为全线未命中，很容易被误读成模型变差。
fn count(value: &str) -> Result<usize, TuneError> {
    let parsed: usize = value
        .parse()
        .map_err(|_| TuneError::Value(value.to_owned()))?;
    if parsed == 0 {
        return Err(TuneError::ZeroLimit(value.to_owned()));
    }
    Ok(parsed)
}

#[derive(Debug, thiserror::Error)]
pub enum TuneError {
    #[error("--tune expects name=value, got {0:?}")]
    Syntax(String),

    #[error("--tune value is not a number: {0:?}")]
    Value(String),

    #[error(
        "--tune limit must be at least 1, got {0:?}; 0 makes whole-sentence conversion return nothing"
    )]
    ZeroLimit(String),

    #[error("unknown --tune name {name:?}; known: {}", KEYS.join(", "))]
    Unknown { name: String },
}

#[cfg(test)]
mod tests {
    use qingjian_dictionary::Dictionary;

    use super::*;

    fn engine() -> Engine {
        Engine::new(Dictionary::parse("我\two\t100\n").unwrap())
    }

    #[test]
    fn empty_settings_keep_defaults() {
        let mut engine = engine();
        apply(&mut engine, &[]).unwrap();
        assert_eq!(engine.interpolation(), Interpolation::DEFAULT);
        assert_eq!(engine.typo_costs(), TypoCosts::DEFAULT);
        assert_eq!(engine.search_limits(), SearchLimits::DEFAULT);
    }

    #[test]
    fn settings_override_only_the_named_values() {
        let mut engine = engine();
        apply(
            &mut engine,
            &["lambda=0.7".to_owned(), " substitute = 5.5 ".to_owned()],
        )
        .unwrap();
        let interpolation = engine.interpolation();
        assert_eq!(interpolation.lambda, 0.7);
        assert_eq!(
            interpolation.confidence_k,
            Interpolation::DEFAULT.confidence_k
        );
        let costs = engine.typo_costs();
        assert_eq!(costs.substitute, 5.5);
        assert_eq!(costs.transpose, TypoCosts::DEFAULT.transpose);
    }

    /// 三个规模参数要能整套扫，且没点的那个保持缺省——扫参时一次只动一个。
    #[test]
    fn search_limits_are_tunable_one_at_a_time() {
        let mut engine = engine();
        apply(&mut engine, &["beam=3".to_owned()]).unwrap();
        let limits = engine.search_limits();
        assert_eq!(limits.beam_width, 3);
        assert_eq!(
            limits.span_candidates,
            SearchLimits::DEFAULT.span_candidates
        );
        assert_eq!(
            limits.abbreviated_span_candidates,
            SearchLimits::DEFAULT.abbreviated_span_candidates
        );

        apply(
            &mut engine,
            &["span=2".to_owned(), "abbreviated-span=9".to_owned()],
        )
        .unwrap();
        let limits = engine.search_limits();
        assert_eq!(limits.span_candidates, 2);
        assert_eq!(limits.abbreviated_span_candidates, 9);
    }

    /// 0 是静默故障：整句转换会直接返回空，评测里表现为全线未命中，
    /// 看着像模型坏了。必须在入口就挡掉。
    #[test]
    fn zero_limits_are_rejected() {
        let mut engine = engine();
        assert!(matches!(
            apply(&mut engine, &["beam=0".to_owned()]),
            Err(TuneError::ZeroLimit(_))
        ));
        assert!(matches!(
            apply(&mut engine, &["span=0".to_owned()]),
            Err(TuneError::ZeroLimit(_))
        ));
        // 被挡下之后引擎没被改坏
        assert_eq!(engine.search_limits(), SearchLimits::DEFAULT);
    }

    /// 规模参数不是浮点：`beam=2.5` 该报错，而不是悄悄截成 2。
    #[test]
    fn fractional_limits_are_rejected() {
        let mut engine = engine();
        assert!(matches!(
            apply(&mut engine, &["beam=2.5".to_owned()]),
            Err(TuneError::Value(_))
        ));
    }

    /// NaN / inf 会让排序比较器全部返回 Equal，结果是静默不排序。
    #[test]
    fn non_finite_numbers_are_rejected() {
        let mut engine = engine();
        for value in ["lambda=NaN", "lambda=inf", "lambda=-inf"] {
            assert!(
                matches!(
                    apply(&mut engine, &[value.to_owned()]),
                    Err(TuneError::Value(_))
                ),
                "{value} 应该被拒绝"
            );
        }
    }

    #[test]
    fn rejects_bad_syntax_values_and_names() {
        let mut engine = engine();
        assert!(matches!(
            apply(&mut engine, &["lambda".to_owned()]),
            Err(TuneError::Syntax(_))
        ));
        assert!(matches!(
            apply(&mut engine, &["lambda=abc".to_owned()]),
            Err(TuneError::Value(_))
        ));
        assert!(matches!(
            apply(&mut engine, &["gamma=1".to_owned()]),
            Err(TuneError::Unknown { .. })
        ));
    }
}
