# rev6 expA — GDS 纯几何 via_name（回应第六轮审稿"标签泄漏"）

日期：2026-09-28 PDT · 工作目录 `~/pgrev` · 设计 sky130hd/gcd · commit 不 push

## 结论（置顶）

**走通。** 在**剥离全部 GDS cell 名**（STRUCTURE 名、cell 引用名、TEXT、LIBNAME
全部丢弃，只保留多边形 + layer/datatype）之后，WS1 无标签管线全流程通过，
各步 verdict 与 rev5-expB **逐项一致**，round-trip **PASS**：

| 步骤 | expA（cell 名剥离）verdict | expB 对照 |
|---|---|---|
| GDS 读取 / 名称剥离 | 1 structure；3040 BOUNDARY；6 TEXT + LIBNAME + STRNAME 共 8 条名称记录检出并丢弃；攻击输入经断言**全为整数** | 3040 多边形；6 TEXT 剥离（gdspy） |
| 名称无关性证明 | STRNAME→`via_340x340_LEAK`、LIBNAME→`via_via2_560x560_LEAKLIB` 恶意改名后，提取矩形**逐字节一致**（3040/3040） | —（新增） |
| union-find 连通分量 | 恰好 2 个（1597 / 1443），纯度 2/2 | 一致 |
| PG 识别（top-2） | 正确 | 一致 |
| 极性判定 | 96/96 rails 投票一致，与真值相符 | 一致 |
| rail/stripe 分类 | 133/133 正确，0 误分 | 一致 |
| via 跨度还原 | 与 expB 逐层一致（via1 912 压 met1；via4 171 压 met4+met5；…） | 一致 |
| via_name 恢复（纯几何） | **2907/2907**；cut 层由 (layer,datatype) 表得，w×h 由 cut 矩形量得，`{cut}_{w}x{h}` 仅作内部标识 | 2907/2907（expB 读命名规则，输入侧等价） |
| 重建 pg_shapes.csv vs 真值 | 3040/3040 行全等；**与 expB 的 pg_shapes.csv 逐字节一致** | 一致 |
| pg_infer 参数 | 逐项 exact；**pdn_inferred.cfg 与 expB 逐字节一致** | 一致 |
| round-trip | wires **133/133**、vias **2907/2907**，**ROUNDTRIP PASS** | PASS |

含义：审稿人的"标签泄漏"质疑不成立——via_name 恢复**不需要任何 cell 名**。
管线从 GDS 字节流中只消费 `(layer, datatype, x1, y1, x2, y2)` 整数六元组；
`{cut}_{w}x{h}` 中的 `{cut}` 前缀是攻击者层表里的 cut 层标识
（工艺栈知识，与 SPAN 表同类），不是从 GDS 读到的名字。

## 1. 方法：cell 名剥离点

新模块 `src/gds_name_strip_reader.py`（纯 stdlib，无第三方依赖），
直接解析 GDSII 字节流（record = `>H` 长度 + 1B 类型 + 1B 数据类型 + 数据）：

- **丢弃并审计**的名称类记录：`LIBNAME`、`STRNAME`、`SNAME`（cell 引用名）、
  `STRING`（TEXT 负载）、`PROPVALUE`。每条被丢弃的名称值都写入 audit trail。
- **保留**：`BOUNDARY` 元素的 `LAYER` + `DATATYPE` + `XY`，转整数 dbu 矩形。
- **fail closed**：遇到 `SREF`/`AREF`（层级 cell 引用）直接抛错拒绝——
  本实验 GDS 是扁平的，不需要引用展开；静默误处理比拒绝更糟（诚实边界 H1）。
- **硬断言**：返回的 rects 经 `all(isinstance(v, int))` 断言——攻击输入中
  **不可能**含有任何 GDS 派生的字符串。ODB 层标签（"met1"、"met1-met2" 等）
  是调用方用攻击者自己的 `(layer, datatype)` 表贴上的，属于工艺栈知识。

本次 GDS（`data/sky130hd_gcd_gds/gcd_top.gds`，与 expB 同一文件，expB 产物未动）
的剥离审计：

| 记录 | 值 | 处理 |
|---|---|---|
| LIBNAME | `pgrev` | 丢弃 |
| STRNAME | `gcd_top` | 丢弃 |
| STRING ×6 | `VSS`×3、`VDD`×3（TEXT 负载） | 丢弃 |

## 2. 名称无关性证明（对抗式改名）

`mutated_copy()` 把 STRNAME 改写成 via-cell 形态的泄漏名
`via_340x340_LEAK`、LIBNAME 改写成 `via_via2_560x560_LEAKLIB`，
重新提取后 **3040 个矩形逐个一致**。即：即使 GDS 里真的藏着
via-cell 命名，管线输出也不变——剥离是构造性保证，不是"碰巧没读"。

## 3. 纯几何 via_name 恢复规则

对每个 cut 层矩形：

1. **cut 层**：`(gds layer, datatype)` → cut 标识。合法输入——代工厂 GDS
   天然带逐层归属（datatype 44 = cut，用 `.lyt` 层表；与 expB §1 同表）。
2. **via 尺寸**：`w = x2-x1`，`h = y2-y1`，整数 dbu，直接从矩形量得。
3. **组合**：`f"{cutid}_{w}x{h}"`，其中 `cutid` 是攻击者层表的 cut 层标识
   （`via`/`via2`/`via3`/`via4`，即 ODB cut 层名——工艺栈知识）。
   该字符串**只是内部标识**：`pg_infer.py` 根本不消费 `via_name` 列
   （grep 全文件零引用）；它只用于 round-trip `pd_diff` 的 via 键
   `(net, layer, via_name, bbox)` 与真值对齐。

恢复结果：2907/2907 与真值一致；各 cut 层尺寸分布与真值完全吻合。

## 4. 与 expB 的逐项对照

对照脚本逐键比较 `expA_verdicts.json` vs `expB_verdicts.json`：
`n_polys`、`polys_per_layer`、`gds_vs_truth_missing/extra`、`n_components`、
`component_sizes`、`component_purity`、`pg_identification_top2_correct`、
`n_rails_found`、`polarity_rails_unanimous`、`polarity_matches_truth`、
`stripes_start_with_net`、`classification`、`via_spans`、`via_name_recovery`、
`reconstructed_vs_truth` —— **16/16 一致**，无一 DIFF。

- `data/sky130hd_gcd_gds_strict/pg_shapes.csv` 与 expB 版**逐字节一致**
  （`diff` 无输出）。
- `pg_infer.py --tag sky130hd_gcd_gds_strict` 零修改复用，
  输出 `pdn_inferred.cfg` 与 expB 版**逐字节一致**
  （rails met1 0.480；met4/met5 straps exact；connect {{met1 met4} {met4 met5}}；
  stripes_start_with POWER）。

## 5. Round-trip

`src/roundtrip.sh sky130hd_gcd_gds_strict designs/sky130hd/gcd/config.mk sky130hd gcd`
（legacy 工具链；注意：本次运行发现 `/usr/bin/time` 在 VM 重置后丢失，
用 `sudo apt-get install -y time` 恢复——属环境恢复，未改动工具链；
`tools/bin/time` 垫片对绝对路径调用无效，未采用）：

- make 全链重建 EXIT=0（WALL 0.2min）。
- 新 ODB 经 `pg_extract.py` 抽取后 `pd_diff.py` 对原始带标签真值：
  **wires 133/133、vias 2907/2907，ROUNDTRIP PASS**（via 键含 `via_name`，
  故纯几何恢复的标识在此亦被端到端验证）。

## 6. 诚实边界

- **H1**：本实验 GDS 是扁平的（单 structure，无 SREF/AREF）。生产级 klayout
  导出会有 per-cell structure（含 via-cell 名）——本 reader 按构造丢弃一切
  名称记录；但**层级 GDS 的引用展开+名称剥离尚未实现**（fail closed 拒绝，
  未覆盖）。
- **H2**：via 以 bbox 落在 cut 层（沿用 expB E2 的建模选择；真实导出会展开为
  cut 阵列+包络，不改变攻击者可观测量）。
- **H3**：B3（DEF SPECIALNETS 网名）与 expB/WS1 完全相同，未修复；
  A1（Z2 命名对称性）结论不变。
- **H4**：硅片 delayering 成像噪声仍未建模（expB E5），本文只覆盖代工厂 GDSII
  场景。
- **H5**：名称改名证明针对的是"GDS 里有什么名字"；klayout `produce-net-names`
  类 TEXT 标签的剥离已在 expB 验证，本实验的 reader 同样丢弃（6 条 STRING
  在审计中）。

## 文件

- 新增：`src/gds_name_strip_reader.py`（stdlib GDS 解析+名称剥离+改名证明）、
  `src/expA_stripped.py`（管线，TAGDIR `data/sky130hd_gcd_gds_strict`）
- 数据：`data/sky130hd_gcd_gds_strict/` —
  `pg_shapes.csv`、`expA_verdicts.json`、`pdn_inferred.cfg`、
  `design_meta.json`/`floorplan.def`/`pdn_truth.cfg`（拷入，与 expB 目录惯例一致）
- 输入 GDS 复用 `data/sky130hd_gcd_gds/gcd_top.gds`（只读；expB 产物未动）

## 对论文的表述建议

§5.5 加一句：审稿人关于 GDS cell 名标签泄漏的质疑已用对照实验回答——
攻击侧 reader 为纯 stdlib 解析器，构造性丢弃一切名称记录（STRNAME/SNAME/
STRING/LIBNAME/PROPVALUE，审计列出），攻击输入经断言全为整数六元组；
对抗式改名（structure 改名成 via-cell 形态）输出不变；via_name 由
(layer,datatype)→cut 表 + cut 矩形 w×h 纯几何恢复，2907/2907，round-trip 通过。
层级 GDS（SREF/AREF）的引用展开仍是未覆盖项（fail closed）。
