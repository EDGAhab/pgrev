# rev6 实验 B：推断器建模 pdngen 浮点截断（1600 组）

日期：2026-09-28 ｜ 工作目录 `~/pgrev` ｜ 代码：`src/expB_truncation.py`，`src/pg_infer.py`（`--hyps-out` 扩展）

## 1. 目标

rev5 实验 D 在广度扫描 800 组中留下 **3 个 fail**，根因是 pdngen 内部的浮点/dbu 裂缝（`float` 坐标经三位 µm 序列化后与整数模型差 1–2 dbu），不是推断器逻辑 bug。本实验把"浮点截断"显式建模为修正步骤，加在 `pg_infer.py` 初推断之后，目标：

- 1600 组（rev5 全部真值：sky130hd/gcd 800、nangate45/gcd 300、asap7/gcd 300、sky130hd/aes 200）**失败归零**
- 候选选择只能依据观测几何，**不许偷看真值**；真值只用于最终 exact/equiv 统计
- 保留约 5 个 genuine equiv（几何上不可区分的对偶）

三指标（rev5 口径）：
- **inference success**：推断器产出几何忠实配置（exact + equiv + unidentifiable）
- **round-trip pass**：反推配置重跑 pdngen，`pd_diff.py` 判定 wire（≤1 dbu）+ via 全等
- **exact**：反推参数与真值逐项一致

## 2. 浮点截断模型

### 2.1 序列化格点

pdngen 配置以十进制 µm 文本书写（`write_cfg` 用 `%.3f`）。DBU=2000 时，**奇数 dbu 值不在可实现格点上**：

```
14263 dbu → 7.1315 µm → "7.131" → 14262 dbu
```

即配置空间先被投影到"三位 µm 可表示"的格点（DBU=2000 下为偶数 dbu），pdngen 实际看到的是投影后的值。所有 hypothesis 与候选在搜索前都经 `ser_val()` 归一化到该格点：

```python
def ser_val(v, dbu):
    return int(round(float(f"{v / dbu:.3f}") * dbu))
```

这一步曾抓到一个真实 bug：nangate45 cfg0046 一度被错选为 `offset+1`，原因正是候选落在不可实现格点上。

### 2.2 pdngen 内部的真实计算路径（源码核验）

核验 legacy `PdnGen.tcl@f12e2f47`：

1. `verify_grid` → `convert_layer_spec_to_def_units` 把 width/pitch/spacing/offset 经 `ord::microns_to_dbu`（round-half-up，实测探针确认）转为 dbu **整数**。
2. `check_straps` 里 `spacing = pitch / 2.0` 的默认值**从未生效**——第 1426–1428 行 `check_straps [dict get $grid straps]` 丢弃了返回值（对比上一行 rails 的 `dict set grid rails [check_rails …]` 保留了返回值）。
3. 无 spacing 层走 `generate_upper_metal_mesh_stripes` 的 else 分支（第 3642、3661 行）：`offset + (pitch / 2)`，此时 pitch 已是 dbu 整数，Tcl `expr` 做**整数除法**（如 `28034/2 = 14017`）。

结论：pdngen 的前向映射在 dbu 整数域是确定的；"裂缝"只出现在 µm 文本 ↔ dbu 整数的两次转换处（配置写入 `%.3f`、内部 `microns_to_dbu` round）。整数模型与 pdngen 的分歧被限制在 ±2 dbu 以内——这就是候选 jitter 范围的依据。

## 3. 修正流程

```
真值配置 → pdngen → 观测几何
    → pg_infer.py（冻结初推断，--hyps-out 输出全部全局一致假设）
    → 初推断重跑 pdngen，与观测做 0-dbu strict wire/via diff
    → 若 diff = 0：直接采用（不触发修正）
    → 若 diff > 0：触发截断建模修正
```

修正搜索空间（**不看真值**）：
- 每个 globally-consistent hypothesis（含 AMBIGUOUS 备选分支——浮点裂缝可能把 tie-break 推到错误分支，其 ±2 dbu 邻域内无 bit-exact 几何）
- × 单参数 ±1、±2 dbu jitter：每层 strap 的 offset、shift（spacing/无 spacing 时的 pitch/2 相位）、width、pitch；rails widths 联动
- 全部限制在序列化格点上（`ser_val(v) == v`）
- 升级：joint (offset × shift) 16 组合/层

每个候选都用**真实 pdngen**重跑，以完整 wire/via 集合的 **0-dbu strict diff** 做选择；平局按 jitter 最小 → hypothesis 排序 → label 字典序（确定性）。真值 JSON 只在最后计算 exact/equiv 时使用。

## 4. 结果

| 设计 | N | inference success | round-trip pass | exact | equiv | fail |
|---|---|---|---|---|---|---|
| sky130hd/gcd | 800 | 800/800 | 800/800 | 798/800 | 2 | 0 |
| nangate45/gcd | 300 | 300/300 | 300/300 | 300/300 | 0 | 0 |
| asap7/gcd | 300 | 300/300 | 300/300 | 299/300 | 1 | 0 |
| sky130hd/aes | 200 | 200/200 | 200/200 | 198/200 | 2 | 0 |
| **合计** | **1600** | **1600/1600** | **1600/1600** | **1595/1600** | **5** | **0** |

rev5 对照：expA（800 组）success 800/800、RT 800/800、exact 798/800；expD（800 组）success 797/800、RT 797/800、exact 794/800。合计旧数字：success 1597/1600、RT 1597/1600、exact 1592/1600，3 fail。

**失败归零**：hard failures（fail/fail_exact_rt/infer_fail/error）= 0；inference success 与 round-trip pass 均为 1600/1600。

修正触发统计：初 strict>0 的 case 共 **3** 个（全部来自 rev5 的旧 fail），经截断建模修正后 **3/3 达到 bit-exact**。其余 1597 组的初推断即 strict diff 0，无需修正。

## 5. 三个旧 fail 的修复

rev5 expD 的 3 个 fail 的修正路径（winning hypothesis / jitter，全部经真实 pdngen 重跑验证、按观测几何 strict diff 选择）：
- nangate45/gcd cfg0046：初 strict 580 → hypothesis-1（dropout 分支的 AMBIGUOUS 备选）零抖动即 bit-exact → **exact**（pilot 阶段曾因并发评测污染误报 fail，见 §7；全量结果干净）
- asap7/gcd cfg0004：初 strict 2260 → hyp0 / M5.shift −1 dbu → strict 0 → **exact**
- asap7/gcd cfg0160：初 strict 110 → hyp0 / M6.shift +2 dbu → strict 0 → **exact**

## 6. Genuine equiv（逐项）

5 个 equiv 全部保留（与 rev5 编目一致，无新增、无丢失）；均为 round-trip pass 的真几何对偶，参数差异如下（真值 → 推断）：

1. sky130hd/gcd cfg0462：starts_with GROUND→POWER；m4.offset 4966→846；m5.offset 540→20481。经典 AMBIGUOUS：starts_with 翻转 + offset 对偶。
2. sky130hd/gcd cfg0578：starts_with GROUND→POWER；m4.offset 418→4920、m4.spacing 2122→16348；m5.offset 362→12052、m5.spacing 10086→8910。广义对偶重参数化。
3. asap7/gcd cfg0161：starts_with GROUND→POWER；M3.offset 1888→121；M6.offset 152→1499。经典 AMBIGUOUS。
4. sky130hd/aes cfg0077：starts_with GROUND→POWER；met4.offset 778→6016、met4.spacing 3204→5096；met5.offset 4480→50、met5.spacing 3556→2810。starts_with + 两层 offset/spacing 重参数化。
5. sky130hd/aes cfg0186：starts_with GROUND→POWER；met4.offset 4866→255；met5.offset 1100→7153。同类 AMBIGUOUS。

注：`starts_with` 翻转本身不改变几何（对称性），offset/spacing 的重参数化在对应 pitch 下产生逐点相同的 strap 集合；这些是 pdngen 参数→几何映射的内禀非单射点，不是推断器错误。

## 7. 诚实边界与事故记录

1. **候选范围 ±2 dbu**：建模假设 pdngen 的浮点裂缝不超过 2 dbu（§2.2 源码核验支持）。超出此范围的裂缝本方法修不了——1600 组中未出现。
2. **依赖已知前向模型**：修正需要调用 legacy pdngen 做真实重跑；不是纯解析的"盲"修正。这是实验设计，不是部署方案。
3. **只覆盖四套保存的扫描**：结论限于 sky130hd/nangate45/asap7 的 gcd/aes 网格配置；ring/macro、商用工具不在范围内。
4. **pilot 并发污染事故**：pilot 阶段曾有 3 个 `pilot` 进程并发执行，共享 `/tmp/rsC/work/{design}_{i}` 与 `cand.cfg/cand.odb` 同名文件，候选评估出现 (config, ODB) 错配，导致 nangate45 cfg0046 误报 fail（单跑即 exact）。worker 的 scratch 路径无并发保护——全量运行为单进程双 worker（case 间路径正交），不受影响。教训：`worker()` 的固定 scratch 路径不是并发安全的。
5. **VM 重启导致 /tmp 全丢事故**：全量首次运行至 771/1600 时 VM 重启，`/tmp/rsC`（771 个结果 JSON）全部丢失。教训：`/tmp` 是 ephemeral 的，结果必须写持久化位置。已将 `RS` 改为 `~/pgrev/work/expB`（持久化），`cmd_run` 支持断点续跑（跳过已有结果 JSON 的 case），`work/` 已加入 `.gitignore`。第二次全量 1600/1600 一次跑完，无中断。
6. `pg_infer.py` 默认 CLI 行为、stdout、`pdn_inferred.cfg` 经回归验证与旧版 **BYTE_IDENTICAL**；`--hyps-out` 为纯加法扩展。

## 8. 交付

- 代码：`src/expB_truncation.py`（新）、`src/pg_infer.py`（`--hyps-out` 加法扩展）
- 本报告：`reports/rev6-expB-truncation-modeling.md`
