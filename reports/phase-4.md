# Phase 4 — PDN 参数反推（inference）

日期：2026-09-26 PDT · 脚本：`src/pg_infer.py` · 输出：`data/<tag>/pdn_inferred.cfg`

## 方法

输入只有 `pg_shapes.csv`（Phase 3 抽取的几何）+ `design_meta.json` + `floorplan.def`
（读 SPECIALNETS 的 USE POWER/GROUND 判定电源/地网名）。不读真值配置。

### 已验证的前向模型（对照 PdnGen.tcl @ f12e2f47）

- **rails**：每行 stdcell 上下边界各一条，宽度 = 配置值；VDD/VSS 归属由 row
  orientation 决定（R0 上边 VDD / MX 相反）。`rails_start_with` 在源码中**从未被读取**
  ——死参数，反推时省略。
- **straps**：设 `ref = (stdcell_xMin, stdcell_yMin − max_rail_width/2)`（源码
  `stdcell_plus_area`，Y 向扩展半个 rail 宽，X 向不扩展）。
  - VDD（base）网格：`ref + offset + k·pitch`
  - VSS 网格：`ref + offset + shift + k·pitch`，其中
    `shift = pitch/2`（无 spacing 时）或 `shift = spacing + width`（有 spacing 时）
  - stripe 循环条件：`center < area_max − width`
  - `stripes_start_with` 决定哪个网是 base 网格（POWER→VDD 先排）。
- **connect**：via 的 `(bottom, top)` 跨度组成链；链内自底向上走，
  `(最低 rail 层 → 其上方第一个 strap 层)` 为 rail→strap 对，
  链内连续 strap 层两两配对为 strap→strap 对。
- rail 的 `pitch/offset`（如 nangate45 的 `pitch 2.4`）不影响 rail 几何
  （缺省时源码自动填 `2×row_height`）；`::halo` 只影响 macro；grid `name` 任意。
  以上在反推输出中全部省略。

## 反推结果 vs 真值（几何相关参数）

| 设计 | rails | straps | connect | starts_with |
|---|---|---|---|---|
| sky130hd/gcd | met1 w0.480 ✓ | met4 {1.600, 27.140, 13.570} ✓；met5 {1.600, 27.200, 13.600} ✓ | {{met1 met4} {met4 met5}} ✓ | POWER ✓ |
| nangate45/gcd | metal1 w0.170 ✓ | metal4 {0.480, 56.000, 2.000} ✓；metal7 {1.400, 40.000, 2.000} ✓ | {{metal1 metal4} {metal4 metal7}} ✓ | POWER ✓ |
| sky130hd/aes | met1 w0.480 ✓ | 同 sky130hd/gcd ✓ | {{met1 met4} {met4 met5}} ✓ | POWER ✓ |
| asap7/gcd | M1/M2 w0.018 ✓ | M5 {0.120, 11.880, 0.300, spacing 0.072} ✓；M6 {0.288, 12.000, 0.513, spacing 0.096} ✓ | {{M1 M5} {M5 M6}} ✓ | POWER ✓ |

✓ = 与真值配置的对应参数**完全一致**（数值到 0.001 µm）。asap7 正确命中了
`if 4X` 分支中的 1X 分支，并正确区分了两种 VSS 相位机制
（pitch/2 vs spacing+width：M5 shift=192dbu=72+120，M6 shift=384=96+288）。

## 不可辨识 / 等价类（记录在案）

1. `::halo`、`::rails_start_with`、rail `pitch/offset`、grid `name`：无几何效应，
   反推省略。v_dead 变体实验证明（见 Phase 5）。
2. macro grid：4 个设计均无 macro，无法从几何中恢复。
3. pin 名、blockage、global connect：不在几何中，无从恢复。
4. 曾假设“单条高跨 connect 对 {{met1 met5}} 与拆分对等价”——**被证伪**：
   高跨对实际产生 0 个 via（见 Phase 5 v_conn），connect 粒度可辨识。
