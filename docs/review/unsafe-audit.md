# unsafe 审计清单

全 workspace 的 `unsafe` 按文件登记，配 [review/unsafe-baseline.json](unsafe-baseline.json) 做**增量门**：
CI 扫出某个文件 `unsafe` 块数**超过**基线 = 新增了没登记的 unsafe → 红（scripts/unsafe_audit.py）。
基线的语义是「现状快照」：任何文件的 unsafe 数量只准减、不准加；真要加，先读下面的纪律，改完更新基线并说明。

## 现状（2026-09-20 首轮核算，共 77 文件 259 块）

- **crates/（核心，8 块）**：这是最该盯的部分。全部是「绑外部不变量」的受控 unsafe：`.qj` 的 mmap 视图
  （`container.rs` 映射、`text.rs` 的 `from_utf8_unchecked`）、candle 的 mmap 权重（`scorer.rs`）、
  DirectWrite FFI（`render/fonts/directwrite.rs`）。每块都有 `// SAFETY:` 论证，详见下方登记。
- **apps/（壳，251 块）**：macOS 壳是 objc2（AppKit / IMK / CoreText）绑定、Windows 壳是 COM（TSF / DirectWrite）
  绑定——这些平台的 FFI 绑定形态本身就需要 unsafe，属合理现状，快照入基线。往壳里加新 unsafe 同样要登记。

## 纪律（什么时候才允许 unsafe）

1. **只做 FFI / 零拷贝视图这一类「绑外部不变量」的事。** 排序、字符串处理、数据结构一律 safe；
   core 的纯逻辑 stream 里出现 unsafe 要格外解释。
2. **每块 unsafe 必须有 `// SAFETY:` 段**，讲清不变量由谁保证、谁验过、怎么验。
3. **能不用就不用**：`.qj` 打开时先整文件校验边界与 UTF-8，映射之后才走 unsafe 读；窗口尽量小。

## 核心层（crates/）登记：8 块

### crates/qingjian-format/src/file/container.rs · 1 块
- `Container::open` 的 `Mmap::map(&file)`：数据文件只整体替换（写临时文件再改名）、从不就地修改，
  映射期间内容不变（`// SAFETY:` 在 34 行）。边界校验全走 safe 路径（`ref_from_bytes` 等 zerocopy 带边界检查）。

### crates/qingjian-format/src/view/text.rs · 1 块
- `Deref::deref` 的 `from_utf8_unchecked`：`Text::mapped` 构造时做过 UTF-8 校验，映射内容生命周期内不变；
  走校验版每次取 `&str` 要扫一遍几十 MB 的 arena（`// SAFETY:` 在 49 行）。

### crates/qingjian-render/src/fonts/directwrite.rs · 5 块
- `system_collection`（14 行）：共享工厂随进程存活，出参按 COM 文档传指针。
- `family_files`（31 行）：只读查询，出参缓冲按报的长度分配。
- `file_path`（74 行）：引用键由 DirectWrite 持有、随 file 存活；路径缓冲按报的长度加终止符分配。
- `families`（94 行）、`localized`（115 行）：只读查询；缓冲按报的长度分配。

### crates/qingjian-neural/src/scorer.rs · 1 块
- `load_directory` 的 `VarBuilder::from_mmaped_safetensors`（60 行）：mmap 权重，模型存活期间文件不改动。

## 计数标准（与 scripts/unsafe_audit.py 一致）

正则 `unsafe\s*\{` 与 `unsafe\s+fn\b` 都算（FFI 绑定可能块或声明任一种形态）。
新增 unsafe 的例行流程：登记到「现状」→ 跑 `python3 scripts/unsafe_audit.py` → 它在通过时会提示同步基线。
