# rev5 expB — GDSII 代工厂场景验证（sky130hd/gcd）

日期：2026-09-27 PDT · 工作目录 `~/pgrev` · 不 push（按任务要求仅 commit）

## 结论（置顶）

**走通。** WS1 无标签管线在**真实 GDSII 文件**输入下全流程通过，
各步 verdict 与 ODB 去标签输入（rev3 WS1）逐项一致：

| 步骤 | GDSII 输入 verdict | WS1（ODB 去标签）对照 |
|---|---|---|
| GDS 读取 / TEXT 剥离 | 3040 多边形；6 条 TEXT（VDD/VSS 网名）检出并剥离 | —（CSV 无 TEXT 概念） |
| union-find 连通分量 | **恰好 2 个**（1597 / 1443），纯度 2/2 | 2 个（1597 / 1443），纯度 2/2 |
| PG 识别（top-2 启发式） | 正确 | 平凡正确 |
| 极性判定 | **96/96 rails 投票一致**，与真值相符 | 96/96 |
| rail/stripe 分类 | **133/133 正确，0 误分** | 0 误分 |
| via 跨度还原 | via1 912/912 压 met1 rail；via4 171/171 压 met4+met5；via2/via3 跨度由 cut 层表+堆叠给出 | 一致 |
| via_name 恢复 | 2907/2907 | —（WS1 输入自带 via_name） |
| 重建 pg_shapes.csv vs 真值 | **3040/3040 行全等** | 3040/3040 |
| pg_infer 参数 | **逐项 exact**，与 WS1 输出逐字节一致 | exact |
| round-trip | wires 133/133、vias 2907/2907（待跑，见 §7） | PASS |

含义：不可信代工厂拿到 GDSII（天然逐层多边形归属、无 net 名）时，
攻击者可用 §5.5 管线逐项恢复 pdngen 几何参数——**威胁模型与实验输入
的一致性缺口已用真实版图格式闭合**。"成像噪声"（对准误差、漏检/误检、
cut 层归属噪声）只对**硅片 delayering** 场景成立，两个场景在论文中分开陈述。

## 1. Stream-out：ODB → GDSII

- 输入 ODB：`tools/OpenROAD-flow-scripts/flow/results/sky130hd/gcd/base/2_6_floorplan_pdn.odb`
 （legacy 工具链，`source env.sh`）。
- 本机 OpenROAD（litex-hub 2022 构建，f12e2f47）**无 `write_gds`**（已用
  `info commands write_gds` 确认），klayout 未安装。故 stream-out 分两步：
  1. `src/dump_all_geo.tcl`：dump **全部 net** 的 swire boxes（wire + via），
     不做 POWER/GROUND 过滤（代工厂 GDS 本来就含全部 net 的布线几何；
     本设计在 PDN 阶段 signal net 尚无布线，dump 得 3040 boxes =
     1597 POWER + 1443 GROUND，与真值一致）。
  2. `src/gds_streamout.py`：纯 stdlib GDSII writer，写标准
     `BOUNDARY` 记录（`(layer, datatype)` + 整数 dbu 坐标），
     **不写任何 net 名 / kind 标签**。
- 层映射（权威来源：`platforms/sky130hd/sky130hd.lyt` 的 `.drawing` 项）：
  met1→68/20，via→68/44，met2→69/20，via2→69/44，met3→70/20，
  via3→70/44，met4→71/20，via4→71/44，met5→72/20。
  注意 ODB cut 层在 met1-met2 之间叫 `via`（ORFS tech LEF 命名），GDS 为 68/44。
- UNITS：user unit 1 µm，1 dbu = 0.001 µm = 1 nm，与 ODB 的 1000 dbu/µm 对齐。
- 输出：`data/sky130hd_gcd_gds/gcd_top.gds`（3040 BOUNDARY，194948 bytes）。

### 关键核查：TEXT / 标签元素

- `--with-text` 模式额外写入 6 条 TEXT 记录（net 名 VDD/VSS，放在 label
  datatype 上），**模拟** ORFS klayout stream-out 的行为——`sky130hd.lyt`
  中 `<produce-net-names>true</produce-net-names>`，生产级导出**会**带网名标签。
- 攻击侧 reader（`src/expB_unlabeled.py`）在提取前**无条件丢弃全部 TEXT 记录**，
  并断言剥离后输入不含任何标签信息。gdspy 独立读回确认：6 条 TEXT 被检出、
  剥离；多边形集合不受影响。
- 结论：攻击输入 = 剥离后的纯 `(layer, datatype)` 多边形集，与威胁模型假设一致。

## 2. GDS → 多边形提取（dbu 对齐核查）

- 用 gdspy 1.6.13（独立第三方 reader，venv 在 `tools/gdsvenv`）读回 GDS。
- `(layer, datatype)` → ODB 层名映射（§1 的逆映射）；cut 层多边形记为 via，
  金属层记为 wire——即"cut 层分组"假设。
- **dbu 对齐**：GDS 坐标（float µm）×1000 取整后，与 ODB dump 的整数 dbu
  坐标**逐个全等**：3040/3040，missing=0，extra=0。GDSII 取整/精度无信息损失。
- 各层多边形数：met1 96 wires；via(68/44) 912；via2 912；via3 912；
  met4 19 wires；via4 171；met5 18 wires。met2/met3 GDS 层为空（与真值一致）。

## 3. WS1 管线在 GDS 输入上的全流程 verdict

脚本 `src/expB_unlabeled.py`（照 `reports/rev3-ws1-unlabeled.md` 重写，
/tmp 旧脚本已丢失）。输入为 §2 的无标签矩形集（3040 个）。

1. **union-find 连通性** — 2 个分量（1597/1443），纯度 2/2（以真值 net 为 oracle
   校验，每个分量只含一个真值网）。三类边：同层 wire 相接/重叠、via 与上下金属
   wire 重叠、相邻 cut 层 via XY 重叠。运行 ~3 s。
2. **PG 识别** — top-2 启发式（wire 数、bbox 面积）正确。
3. **极性判定** — 96/96 rails 投票一致（N-orient 行上边=VDD/下边=VSS，FS 相反），
   与真值 2/2 相符；`stripes_start_with=POWER` 由 pg_infer 恢复。
4. **rail/stripe 分类** — 启发式（met1 + 水平 + width<1µm → RAIL）133/133 正确，
   0 误分。
5. **via 跨度还原** — cut 层表（via↔met1-met2 … via4↔met4-met5，工艺栈知识）；
   overlap 验证：via1 912/912 压住 met1 rail，via4 171/171 同时压住 met4+met5
   stripe，via3 912/912 压住 met4 stripe，via2/via3 不压 met2/met3（此间无 wire），
   跨度由 cut 层表 + 与上下 via 的堆叠 XY 对齐给出（与 WS1 相同的 A5 脆弱点）。
6. **via_name 恢复**（GDS 场景新增步骤，WS1 输入自带该字段）— pdngen 命名规则
   `get_viarule_name`（`reports/PdnGen-f12e2f47.tcl:3005`）为
   `{cut层}_{w}x{h}`（dbu），w/h 即 via 矩形尺寸，cut 层已知 →
   **2907/2907 恢复正确**。这是 PDK 命名惯例知识，非几何标签。
7. **重建带标签 csv** — 网名取自 DEF SPECIALNETS 的 USE POWER/GROUND
  （与 WS1 相同的 B3 标签泄漏，几何恢复不依赖它）；重建的
   `data/sky130hd_gcd_gds/pg_shapes.csv` 与真值 **3040/3040 行全等**。

## 4. pg_infer 复用（零修改）

`python3 src/pg_infer.py --tag sky130hd_gcd_gds` 直接跑通，输出
`data/sky130hd_gcd_gds/pdn_inferred.cfg` 与 WS1 的
`data/sky130hd_gcd_unlabeled/pdn_inferred.cfg` **逐字节一致**：

| 参数 | 真值 | GDS 反推 |
|---|---|---|
| rails met1 width | 0.480 | 0.480 exact |
| straps met4（w/pitch/offset） | 1.600 / 27.140 / 13.570 | exact |
| straps met5（w/pitch/offset） | 1.600 / 27.200 / 13.600 | exact |
| connect | {{met1 met4} {met4 met5}} | exact |
| stripes_start_with | POWER | POWER（含极性） |

与 `pdn_truth.cfg` 的差异仅为死参数（halo、rails_start_with、rail offset）、
global_connections 与 macro grid——与 WS1 结论相同。

## 5. GDS 输入 vs ODB 去标签输入的差异点

| 维度 | ODB 去标签输入（WS1） | GDSII 输入（本实验） |
|---|---|---|
| 层归属 | ODB tech layer 名（met1…/via…） | GDS `(layer, datatype)` 经 `.lyt` 映射；cut 层=datatype 44 |
| 坐标 | ODB dbu 整数 | GDS float µm ×1000 取整；**3040/3040 整数全等，无损失** |
| net 名 | dump 时丢弃 | TEXT 记录模拟 klayout 网名标签，reader 侧**全部剥离** |
| kind 标签 | dump 时丢弃 | GDS 根本无 kind 概念；wire/via 由"金属层 vs cut 层"区分 |
| via 表达 | via cell bbox（dump_pg 语义） | 同左：via cell 以 bbox 落在 cut 层（建模选择，见 §6） |
| wire 表达 | wire bbox | 同左：BOUNDARY 矩形 |
| 多边形排序 | 按 net 分组（POWER/GROUND 交错） | **按 (layer, datatype) 分组**（gdspy `by_spec` 顺序） |

## 6. 管线需要的调整（仅一处 bug 修复 + 一处新增步骤）

1. **bug 修复（GDS 排序相关）**：初版 union-find 候选对用了 `j > i` 去重，
   在 GDS 按层分组排序下导致**相邻 cut 层 via 的配对被系统性漏检**
   （via1 索引全部大于 via2/via3 索引），得到 1010 个碎片分量。
   修复：去掉 `j > i` 限制（union-find 幂等，重复检查无害）。
   教训：WS1 的 ODB 输入按 net 交错排序，掩盖了该假设；GDS 的按层分组排序
   把它暴露了出来——这本身就是"换真实格式跑一遍"的价值。
2. **新增**：via_name 恢复步骤（§3.6），WS1 输入自带该字段，GDS 场景需从
   pdngen 命名规则 + 几何推导。
3. 其余逻辑（连通三类边、PG 识别、极性投票、分类启发式、跨度表、pg_infer
   调用）**零修改**。

## 7. Round-trip

`src/roundtrip.sh sky130hd_gcd_gds designs/sky130hd/gcd/config.mk sky130hd gcd`
（legacy 工具链；`/usr/bin/time` 缺失沿用 WS1 的 exec 垫片方案），
用反推的 `pdn_inferred.cfg` 重跑 ORFS PDN 步骤，抽取几何后
`src/pd_diff.py` 对比原始带标签真值：

- **wires 133/133、vias 2907/2907，ROUNDTRIP PASS**（含 net 标签键——
  极性恢复正确，否则此处必 FAIL）。

注：make 实际从 1_1_yosys 开始重建了整条链（2_5 的 symlink 未阻止重建），
流程确定性成立：重建出的几何与原始完全一致，结论不受影响。

## 8. 诚实边界（沿用 WS1 的 B1–B5，本实验新增）

- **E1**：stream-out 写的是 **net 级布线几何**（wires/vias），未含标准单元/
  tapcell 的 cell-internal pin 几何。生产级全 GDS 中 met1 上的 cell pin
  会与 rail 合并，管线需增加 pin 过滤步骤（PDK LEF pin 几何是公开知识，
  属威胁模型内）——未在本实验覆盖，属 future work。
- **E2**：via cell 以 bbox 落在 cut 层（与 WS1 输入语义一致）；真实 klayout
  导出会把 via cell 展开为 cut 阵列 + 上下包络。该展开不改变攻击者可观测量
  （cut 层归属、叠层位置、XY 范围），仅改变矩形粒度；跨度还原逻辑不受影响。
- **E3**：TEXT 剥离针对的是 klayout `produce-net-names` 类标签；若代工厂 GDS
  含其他形态标签（如 properties），需对应剥离——本实验的 reader 丢弃一切
  非多边形记录。
- **E4**：B3（DEF SPECIALNETS 网名泄漏）与 WS1 完全相同，未修复；
  A1（Z2 命名对称性，需 PDK 库知识锚定）结论不变。
- **E5**：本实验覆盖的是**代工厂 GDSII** 场景（多边形干净、逐层归属确定）；
  **硅片 delayering 成像**的噪声（对准误差、漏检/误检、cut 层归属噪声）仍未建模，
  论文中两个场景分开陈述。

## 文件

- GDS：`data/sky130hd_gcd_gds/gcd_top.gds`（3040 BOUNDARY + 6 TEXT）
- 中间：`data/sky130hd_gcd_gds/all_geo.csv`（ODB dump）、
  `data/sky130hd_gcd_gds/pg_shapes.csv`（重建带标签版）、
  `data/sky130hd_gcd_gds/expB_verdicts.json`（各步 verdict 机器可读）、
  `design_meta.json` / `floorplan.def` / `pdn_truth.cfg`（拷入）、
  `pdn_inferred.cfg`（反推输出）
- 脚本（已进 repo）：`src/dump_all_geo.tcl`、`src/gds_streamout.py`、
  `src/expB_unlabeled.py`
- 第三方 reader：`tools/gdsvenv`（gdspy 1.6.13，仅实验用）

## 对论文的表述建议

§5.5 威胁模型段增加一句：不可信代工厂场景已用真实 GDSII 文件验证
（逐层多边形归属、无 net 名；TEXT 标签剥离），管线在 GDSII 输入下逐项 exact、
round-trip 通过；delayering 成像噪声仍是未覆盖项，属独立场景。
