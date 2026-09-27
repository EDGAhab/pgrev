# WS3: core ring / macro grid 反推验证（rev3，带标签）

日期 2026-09-27。回应审稿人"评估规模小""最有 IP 价值的部分未覆盖"：把 Phase 1–5 的 stdcell
反推方法论扩展到 **core ring** 与 **macro grid**。两者均为带标签验证（net/layer 已知），
对标 Phase 1–5。

结论一句话：ring 参数 6/6 exact、round-trip 全同；macro straps 6/6 exact、connect 链全恢复、
blockages 部分可辨识（含一个 legacy quirk），round-trip 全同。**scope 未缩减。**

## 1. 设计选择

| 实验 | 设计 | 真值来源 | 选择理由 |
|---|---|---|---|
| core ring | sky130hd/gcd | 自写 truth cfg（chameleon 式 `core_ring` + `core_offset`） | gcd core margin 10.12/11.2µm，能容下 ring（w2.0/s2.0/o4.0，外圈伸出 9.0µm）；aes margin 仅 2.3µm，core_offset ring 会画出 die 外，故不用 aes |
| macro grid | nangate45/gcd + fakeram45_32x64（36.86×47.6µm，塞进 80×80µm core） | nangate45_gcd/pdn_truth.cfg **自带**两套 macro grid spec | 真值 cfg 本来就有 macro grid（orient R0/R90 两套），之前因无 macro 而静默 inert——加 macro 即成完美对照实验；fakeram45_32x64 是最小的 fakeram，VDD/VSS pin 在 metal4 上 |

macro instance 以 FIXED 方式加入 DEF（`ram1 fakeram45_32x64 + FIXED (60000 60000) N`，dbu=2000），
经 Tcl（read_lef tech+stdcell+fakeram → read_def → write_db）建成 `gcd_macro_floorplan.odb`。
DEF 的 SPECIALNETS 有 `( * VDD )` 通配符，read_def 后 ram1 的 VDD/VSS pin 自动连到 PG net。

Legacy 源码依据：`src/pdn/src/PdnGen.tcl @ f12e2f47`（从 GitHub 按 commit 取的单文件，
存 /tmp/rev3/ws3/PdnGen.tcl）。

## 2. Ring：参数可辨识性

真值（自设，`/tmp/rev3/ws3/gcd_ring_truth.cfg`）：
```
core_ring {
    met4 {width 2.0 spacing 2.0 core_offset 4.0}   # vertical
    met5 {width 2.0 spacing 2.0 core_offset 4.0}   # horizontal
}
```

前向语义（`generate_core_rings`）：pg_nets 顺序 = [primary_power, primary_ground, …]，
第 i 个 net 的 ring 中心线在 core 边缘外 `core_offset + i*(width+spacing)`；
每 net 每 layer 画 2 条（horizontal layer 上下两条，vertical layer 左右两条）。

反推（`src/pg_infer_ring.py`）：ring bar 是**唯一**中心落在 core 短轴范围之外的 wire rect
（stdcell straps 会被自动延伸到外圈边缘，但中心仍在 core 内——见 §4 quirk 4）。
每 net 每 side 独立测量 offset，共 4 个 side 测量。

| 参数 | 真值 | 反推 | 4-side spread |
|---|---|---|---|
| met4 width | 2.0 | 2.000 | 0 dbu |
| met4 spacing | 2.0 | 2.000 | 0 |
| met4 core_offset | 4.0 | 4.000 | 0 |
| met5 width | 2.0 | 2.000 | 0 |
| met5 spacing | 2.0 | 2.000 | 0 |
| met5 core_offset | 4.0 | 4.000 | 0 |

**6/6 EXACT。** 内圈=VDD、外圈=VSS（pg_nets 顺序决定，power 在内）。
`pad_offset` 语义未测：需要 pads 存在，本设计无 pads；几何上 core_offset 假设已精确重建，
pad_offset 变体列为未覆盖（见 §5）。

## 3. Macro grid：参数可辨识性

真值（nangate45_gcd/pdn_truth.cfg 第一套 macro grid）：
```
orient {R0 R180 MX MY}; power_pins "VDD VDDPE VDDCE"; ground_pins "VSS VSSE"
blockages "metal1 metal2 metal3 metal4"
straps { metal5 {width 0.93 pitch 10.0 offset 2} ; metal6 {width 0.93 pitch 10.0 offset 2} }
connect {{metal4_PIN_ver metal5} {metal5 metal6} {metal6 metal7}}
```
（第二套 orient R90…：无对应 instance，inert——反推正确报告"无证据"，见 §5。）

反推（`src/pg_infer_macro.py`，输入 pg_shapes.csv + design_meta.json macro 位置 + LEF macro 尺寸）：

**straps（6/6 EXACT）**

| layer | width | pitch | offset（macro 边缘→首条中心线） | 顺序 |
|---|---|---|---|---|
| metal5 (hor) | 0.930 ✓ | 10.0 ✓ | 2.000 ✓ | VSS,VDD ✓ |
| metal6 (ver) | 0.930 ✓ | 10.0 ✓ | 2.000 ✓ | VSS,VDD ✓ |

macro straps 恰好铺满 macro bbox（x 60000–133720，y 60000–155200 dbu），共 9+7 条。
（注：pitch 必须按单 net 算——VSS/VDD 交错使相邻中心距只有 5.0µm；初版脚本曾误报 5.0，已修正。）

**connect（全恢复）**

| 真值对 | 几何证据 |
|---|---|
| {metal4_PIN_ver metal5} | 80 个 metal4-metal5 via，via_name=`via4_560x1860`——x 宽 560dbu=0.28µm 正好是 macro pin 宽（strap-strap via 是 960dbu 宽），pin x 位置 pitch 1.68µm、首个在 macro 内 1.96µm，与 LEF pin 位置吻合 |
| {metal5 metal6} | macro bbox 内 32 个 `via5_1860x1860` |
| {metal6 metal7} | macro bbox 内 10 个 `via6_1860x2800`（metal7 stdcell straps 未被 block，从 macro 上方穿过） |

**blockages（部分可辨识 → 上确界等价）**

观测到被切断的 stdcell 层：只有 **metal4**（VDD metal4 strap 在 macro y-range 处断开，
gap 60170–155030 dbu ≈ macro 60000–155200）。真值写的是 metal1–4，但：
- metal1 followpin rails **未被切断**（34 条穿过 macro，legacy quirk，见 §4）；
- metal2/metal3 本设计无 stdcell straps，不可观测。

即真值 blockages 是观测等价类的一个上确界；反推得到最小可观测集合 {metal4}。
Round-trip 用 `blockages "metal4"` 即精确重建（§6），证实歧义无几何后果。

**不可从 PDN 几何恢复的**：`power_pins`/`ground_pins` 的 pin **名字**
（VDD/VDDPE/VDDCE——几何只给出 pin 位置，名字需 LEF；round-trip 用 "VDD"/"VSS" 几何全同）、
`orient` 选择器（DEF 已知 instance orient=R0）。

## 4. Legacy quirk 记录（OpenROAD f12e2f47 PdnGen.tcl）

1. **check_layer_spacing 报错路径自带 SWIG TypeError**：`check_layer_spacing` 的 PDN 79
   报错信息里调 `ord::dbu_to_microns $minSpacing`，而 `$minSpacing` 是 int dbu，
   该 conda 构建要求 double——于是真正的报错（"spacing 1.5 < met5 最小 1.6µm"）
   被 `TypeError in method 'dbu_to_microns', argument 1 of type 'int'` 掩盖。
   初版 ring cfg（spacing 1.5）即因此失败，改 2.0 后通过。注意 met5 的最小 spacing
   是 1.6µm（注释掉的 `#SPACING 1.6` 仍被解析），met4 是 0.3µm。
2. **PDN-0042：pin↔strap via 要求 pin 完全覆盖 strap 宽度**：macro pin（0.28µm 宽）
   与 macro strap（0.93µm）交叠时，只有交叠盖住 strap 全宽才打 via；
   pin 端部与边缘 strap 的部分交叠被跳过。本次 87 个 pin 里 80 个打了 via，
   7 个被跳过——确定性行为，round-trip 精确重建。
3. **blockages 不作用于 followpin rails**：`merge_stripes` 只对 `stripe_locs` 做
   `subtractSet`，rails（FOLLOWPIN）走另一条路径，`blockages "metal1 …"` 写了也白写——
   metal1 rails 穿过 macro 不受影响。
4. **有 core ring 时 stdcell straps 自动延伸到外圈边缘**：`generate_via_stacks`
   把 grid area 重算进 ring area，straps 向外伸到 VSS 外圈的外边缘
   （gcd：x 1120–278560 dbu）。这是 ring 存在即触发的确定性后果，非独立参数；
   反推时靠"中心是否在 core 短轴内"区分 straps 与 ring bars。
5. **macro strap 层自动并入 blockages**：spec 里 `straps` 出现 metal5/metal6 即自动
   `lappend blockages $strap_layer`（PdnGen.tcl:1571）。
6. **via-stack 落点伪影**：dump 里 via stack 位置有多余的微小 wire rect
   （如 metal7 上 0.48×1.4µm 与 via 同框），strap 分析时需按长度过滤
   （本脚本用 >20000dbu 才算 strap）。
7. **Tcl 行内 `#` 不是注释**：inferred cfg 里若带 `# hor, …` 行内注释，
   `#` 会被当成 layer 名 → `PDN-0076 Layer # not found`。round-trip 前已 strip。

## 5. 未覆盖 / 歧义（诚实清单）

- `pad_offset` 语义的 ring：本设计无 pads，未生成、未反推。core_offset 路径 6/6 exact。
- 第二套 macro grid（orient R90…）：无 instance 命中，零几何痕迹——正确识别为"无证据"，
  这本身是一个可辨识性结论（inert spec 不可恢复也不影响几何）。
- blockages 真值 {metal1..4} vs 反推 {metal4}：超集等价，round-trip 证实几何全同。
- power/ground pin 名字、orient 选择器：需 LEF/DEF，不在 PDN 几何内。
- macro 旋转（R90/MX 等）：fakeram 只测了 R0（orient N）；旋转后的 `_PIN_hor` 路径未测。

## 6. Round-trip 结果

| 实验 | inferred cfg | wires orig=rt | vias orig=rt | 结论 |
|---|---|---|---|---|
| ring (sky130hd/gcd) | baseline truth + inferred `core_ring`（§2） | 141 = 141，差异 0 | 2989 = 2989，差异 0 | **PASS** |
| macro (nangate45/gcd) | truth stdcell + 单套 inferred macro grid（§3；blockages 用观测到的 `metal4`，pin 名用 `VDD`/`VSS`） | 84 = 84，差异 0 | 350 = 350，差异 0 | **PASS** |

判据同 Phase 5（`src/pd_diff.py`）：wire box multiset 全同（2dbu 量化后 0 差异）、
via set（net,layer,via_name,box）全同。Macro round-trip 特别说明：
用**缩减版** blockages（metal4 vs 真值 metal1–4）和**缩减版** pin 名仍得全同，
直接证实了 §3 的"超集等价"判断。

## 7. 文件与复现

- 报告：本文件。
- 反推脚本（已进 repo）：`~/pgrev/src/pg_infer_ring.py`、`~/pgrev/src/pg_infer_macro.py`。
- Scratch（/tmp，重启后消失）：`/tmp/rev3/ws3/`——`gcd_ring_truth.cfg`、
  `gcd_ring_inferred.cfg`、`gcd_macro_inferred.cfg`、`gcd_macro_floorplan.def`、
  `run_pdngen.tcl`、`build_macro_odb.tcl`、`ring/`、`ring_rt/`、`macro/`、`macro_rt/`（odb+csv+log）。
- 关键参数全文已记入本报告 §2–§3，可据此重建 cfg。
- 未进 repo：odb/csv（海量中间文件）、`reports/phase-3_ws3_*.png`（pg_extract 自动画的诊断图，
  留在 reports/ 未 commit）。

## 8. 对审稿意见的回应口径（给 parent）

- "评估规模小"：在原有 4 个 stdcell 配置之外，新增 **2 类 PDN 结构**（core ring、
  macro grid）的反推验证，各自独立 round-trip PASS。
- "最有 IP 价值的部分未覆盖"：macro grid（ straps over macro / pin hookup /
  blockages / connect 链）已覆盖；ring 覆盖。SRAM macro 用的是 nangate45 fakeram
 （开源 PDK），方法对商业 SRAM 同理。
- 诚实边界：pad_offset ring、旋转 macro 的 `_PIN_hor` 路径、pin 名/orient 选择器
  仍未覆盖——可列为 future work，不影响"ring+macro 可反推"的主张。
