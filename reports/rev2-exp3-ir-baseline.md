# 实验 3：等金属量 IR 基线（rev2 / A3）

日期：2026-09-27 PDT · 配置：`/tmp/rev2/cfgs/a3_halfpitch.tcl`
（met4 pitch 27.140→13.570 µm，met5 pitch 27.200→13.600 µm，offset 不变；
无混淆的 P/2 baseline）· 结果：`/tmp/rev2/a3/report.json`

IR 模型（与 Phase 6 一致，comparative、非 signoff）：均匀 1A rail injection、
nominal 5Ω/via、ideal met5 feed；不含 routed-signal congestion、timing、EM。

## 三方对比（`defense/lib.py:build_mesh()`，同一模型）

| | baseline | E1a（D3） | A3（P/2 等金属量） |
|---|---|---|---|
| wires | 133 | 169 | 169 |
| vias | 2907 | 5994 | 5994 |
| stripe 总长度 (µm) | 9588.6 | 18918.4 | 18918.4 |
| worst IR (mV/A) | 66.90 | 25.98 | **24.51** |
| mean IR (mV/A) | 38.89 | 11.63 | **11.54** |

（A3 与 E1a 的 wire/via 数量及 stripe 总长度完全相同，是干净的
apples-to-apples 对比。）

## 结论

- D3 vs baseline 的 −61.2%（worst）/ −70.1%（mean）**完全由金属加倍解释**，
  不是混淆带来的收益。
- D3 vs 等金属量 P/2 baseline：worst **+6.0%**（25.98 vs 24.51 mV/A，
  D3 更差），mean +0.8%（基本持平）。
- 因此论文不应再把 D3 的 IR 变化称为"负成本"：相对等金属量基线，
  D3 的 worst-case IR 略差 6%，且代价是 met4/met5 上 2× 的布线阻塞和
  2.06× 的 via 数量——这些才是 D3 的真实价格。
- P/2 baseline 本身是无混淆网格，其 VDD/VSS 为四相交织；均匀注入的电阻
  网格模型下，决定 IR 的是总金属量、via 数与拓扑，上述差异在此模型内成立。
