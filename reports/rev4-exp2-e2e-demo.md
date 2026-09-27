# rev4 实验 B — 端到端攻击演示：spec 捕捉的是设计意图，而非冻结的多边形

日期：2026-09-27 PDT · 工作目录 `~/pgrev` · 实验材料 `reports/rev4-exp2-e2e/`

回应第四轮审稿人第 1 点：**"spec 比几何多出的价值没被证明"**。
本实验展示完整链条——**无标签多边形 → 恢复 spec → 新场景（floorplan 变更）重生成**——
证明恢复出的 spec 是可执行的**参数化规则**（设计意图），而不只是对原几何的冻结拷贝。

## 实验设计

- **起点**：WS1 无标签管线对 sky130hd/gcd 的产出
  `data/sky130hd_gcd_unlabeled/pdn_inferred.cfg`
  （rails met1 w0.480；straps met4 w1.600/p27.140/o13.570，met5 w1.600/p27.200/o13.600；
  connect {{met1 met4} {met4 met5}}；stripes_start_with POWER）。
- **Floorplan 变更（方案 a，优先项）**：取 PDN 前的数据库
  `flow/results/sky130hd/gcd/base/2_5_floorplan_tapcell.odb`，导出 DEF，
  在 core 中央插入一个 50×50µm 的假 macro
  （`FAKE_MACRO_0`，`FAKE_SRAM`，`CLASS BLOCK`，`PLACED (130000 130000) N`，
  即 (130,130)–(180,180)µm；core 为 (10.12,10.88)–(269.56,269.28)µm）。
- **重生成配置**：恢复的 stdcell spec **逐字复用**，另加一段设计师在新 floorplan 下
  本就会写的 macro grid（`orient` / `blockages "met4 met5"` / `halo 2µm`）。
  该段不携带任何 stripe 几何，只声明避让层与 halo（见诚实边界 B2）。
- **运行**：独立 Tcl（`reports/rev4-exp2-e2e/run_pdn_newfloor.tcl`）——
  `read_lef`（tech + merged stdcell + `fake_macro.lef`）→ `read_def`（新 floorplan）→
  `source pdn_newfloor.cfg` → `pdngen -verbose` → `write_db`。
  日志 `pdn_newfloor.log`：**0 error，无 PDN-0042/0079 类报错**，
  `Inserting macro grid for 1 macros ... FAKE_MACRO_0`，stdcell grid 正常插入。

## 结果 1：重生成合法且自适应（新几何）

旧 3040 shapes（133 wires / 2907 vias）→ 新 2926 shapes（141 wires / 2785 vias）：

| net | layer | kind | 旧 | 新 | 说明 |
|---|---|---|---|---|---|
| VDD/VSS | met1 | wire | 48/48 | 48/48 | rails 跟行走，不受 macro 影响 |
| VDD | met4 | wire | 10 | 12 | 2 条被 macro 切断 → 4 段（+2） |
| VSS | met4 | wire | 9 | 11 | 同上 |
| VDD/VSS | met5 | wire | 9/9 | 11/11 | 同上 |
| VDD | met4-met5 | via | 90 | 86 | macro 内 4 个交叉点的 via 栈消失（2 net × 2×2） |
| VSS | met4-met5 | via | 81 | 77 | 同上 |
| VDD | met1-2/2-3/3-4 | via | 480 | 462 | 被切除 stripe 段上的 via 栈消失 |
| VSS | met1-2/2-3/3-4 | via | 432 | 412 | 同上 |

合法性核验（`pg_shapes_new.csv` 全量几何检查）：

- **避让**：met4/met5 stripe wire 进入 macro 矩形 (130–180µm)² 的数量为 **0**；
  via rect 落在 macro 矩形内的数量为 **0**。8 条被切断的 stripe
  （met4：x=132.25/145.82/159.39/172.96µm；met5：y=133.04/146.64/160.24/173.84µm）
  各断为 2 段，16 个断端**精确止于 halo 边界**
  （x 向 128.0/182.0µm，y 向 128.24/181.76µm，y 向含 legacy 脚本固有的 rail_width/2 项）。
- **via 栈完整**：全部 163 个现存 met4×met5 交叉点（86 VDD + 77 VSS）**逐一配有 via4 栈，0 缺失**；
  via1/2/3 每个都落在 met1 rail 与现存 met4 段的交叉上，数量与几何交叉数逐项一致
  （VDD 462/462，VSS 412/412，三层 cut 层各自独立验证）。
- 结论：恢复出的 spec 在新 floorplan 上生成了**合法、完整、自适应避让**的 PDN——
  这是参数化规则重放，不是多边形拷贝。

## 结果 2：对照组——朴素复制原始多边形

把原始 `pg_shapes.csv` 的 wire/via 矩形**原坐标**直接放到新 floorplan 上（die/core 未变，这是对复制法最有利的情形）：

- **8 条 stripe 直接穿过 macro 矩形**（met4 ×4：VDD 2 + VSS 2；met5 ×4：VDD 2 + VSS 2）——短路。
- **122 个 via rect 完全落在 macro 矩形内**（46 个不同的 via-stack XY 位置；
  其中 8 个 met4–met5 栈的上下两层 metal 在新几何中根本不存在 → 死 via；
  其余 met1–met4 链的 via 压在 macro 上）。
- 图 `reports/rev4-exp2-e2e.png`（下图 zoom 95–215µm）：左 = 重生成（stripe 在 halo 处整齐断开），
  右 = 朴素复制（8 条 stripe 穿 macro 而过）。

## 诚实边界（必须与结果一起读）

- **B1 — 同一生成器内重生成**：本实验在 legacy OpenROAD PdnGen（Tcl）内完成，
  证明的是"spec 可跨 floorplan 执行"，**不证明跨工具迁移**（如 Innovus addStripe）。
  跨工具语义映射是另一项工作（rev4 task C 已做文档级分析）。
- **B2 — macro grid 段非反推所得**：原设计无 macro，几何中不存在 macro 规则信息
  （WS1 报告 A4）。实验所加的 macro grid 段是设计师在新 floorplan 下的标准写法，
  不携带 stripe 几何；被验证的参数化规则（rails/straps/connect/starts_with）全部来自反推。
- **B3 — 对照组是朴素基线**：聪明的攻击者会尝试平移对齐/手动修补。
  但 macro 插入后**不存在**使全部 3040 个形状同时合法的刚性变换；
  手动修补 8 条穿 macro stripe + 122 个死 via 不随设计规模扩展——
  参数化重生成是唯一系统化、可扩展的方案。
- **B4 — halo 单位 quirk（已修正并披露）**：legacy `specify_grid` 对 macro halo
  **不做 micron→dbu 转换**（`define_pdn_grid` 会）。首次运行 `halo {2 2 2 2}`
  实际生效仅 2 dbu≈0，y 向切割线因 `set_instance_halo` 的 `-(-rail_width/2)` 项
  落在 macro 边缘内 0.24µm。改用 dbu 值 `halo {2000 2000 2000 2000}` 后切割精确落在
  halo 边界。本报告所有数字来自修正后的运行；quirk 本身是生成器脚本的 bug，
  与恢复 spec 的正确性无关。
- **B5 — met1 rails 仍从 macro 下穿过**：`blockages` 只列了 met4/met5
  （与平台原 macro grid 语义一致：避让的是 stripe 层）。legacy pdngen 的 rails
  跟行走、不跟 placement blockage；真实流程中 macro 下无标准单元是 placement 侧保证的。
  本演示的"避让"指 stripe/via 栈，不含 rails。
- **B6**：网名/单元名仍是标签（WS1 A2），本演示不涉及命名问题。

## 一句话结论

同一份反推 spec，在插入 50×50µm macro 的新 floorplan 上重放出 2926 个形状的合法 PDN
（8 条 stripe 自动在 halo 处断开、163/163 交叉点 via 栈完整、0 error）；
而把原始 3040 个多边形直接复制过去会留下 8 条穿 macro 短路 stripe 和 122 个死 via。
**Spec 的价值 = 可执行的意图；几何的价值 = 一次性的实例。**

## 可复现

- `reports/rev4-exp2-e2e/`：`run_pdn_newfloor.tcl`、`pdn_newfloor.cfg`、
  `fake_macro.lef`、`pdn_newfloor.log`、`pg_shapes_new.csv`、`plot_compare.py`
- `reports/rev4-exp2-e2e.png`：对比图
- 前置：`source ~/pgrev/env.sh`；输入 `flow/results/sky130hd/gcd/base/2_5_floorplan_tapcell.odb`
  （导出 DEF 后插入 COMPONENTS 行，见 `plot_compare.py` 同目录实验记录——
  实际插入用一次性 python 脚本完成，逻辑：COMPONENTS 1132→1133 并追加
  `- FAKE_MACRO_0 FAKE_SRAM + PLACED ( 130000 130000 ) N ;`）
