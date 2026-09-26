# Phase 6 — Defense 实验（E1/E2/E3）

日期：2026-09-26 PDT · 工作目录：`~/pgrev/defense/`
前置：`reports/defense-design.md`（设计）、`reports/phase-4.md`（攻击）、`reports/phase-5.md`（往返）

## 方法说明（相对设计文档的替换，诚实记录）

1. **几何操作层面**：设计文档建议用 ODB Tcl 后处理版图。实际执行改为
   **extracted-geometry 层面**（直接操作 `pg_shapes.csv`），理由：
   反推器 `pg_infer.py` 的**全部输入**就是该 CSV + `design_meta.json` +
   `floorplan.def`，攻击者侧测量与 ODB 路线完全等价；防守者侧判据
   （连通性、spacing、电阻 mesh）同样可从该几何完整计算。
   唯一的诚实缺口：decoy 版图的信号线 DRC 未建模——但 decoy 位于
   P/4 间隙（5.19µm），远离任何 DRC 风险区，已用 LEF spacing 规则验证。
2. **E1b（P/2 decoy）不可行**：实现时发现 +P/2 decoy 恰好落在对方网的
   stripe 中心上（VSS 网格 = VDD 网格 + P/2），即 VDD/VSS 短路。
   同层同网 P/2 交织 decoy 在物理上不存在——设计文档的该变体被证伪，
   未执行。E1 只跑 P/4（E1a）。
3. **E3b roundtrip 未实际重跑 pdngen**：误判 connect 的几何后果用解析
   投影给出（机制同 phase-5 v_conn），报告中明确标注。
4. **Mesh 为对比性指标，非 signoff**：均匀 rail 电流注入、met5 理想馈电、
   标称 via 电阻 5Ω、无封装模型。绝对值仅具相对意义。

工具链核查（本任务实测，非沿用文档）：
- `dump_pg.tcl:7-9`：只遍历 `POWER`/`GROUND` sigType net——悬空 decoy
  在抽取阶段即被过滤（D1a 对照的机制依据）。
- LEF（`sky130_fd_sc_hd.tlef`，实测 grep）：met1/met4/met5 RPERSQ =
  0.125/0.047/0.0285 Ω/□；min spacing met4 = 0.3µm、met5 = 1.6µm。
- 系统 python3：scipy 1.11.4 / numpy 1.26.4（conda env 内无 scipy，
  改用 `/usr/bin/python3`）。

脚本：`defense/lib.py`（mesh/连通性/spacing/反推 runner）、`run_e1.py`、
`run_e2.py`、`run_e3.py`、`robust_pitch.py`（鲁棒攻击者）、
`subset_attack.py`（子集枚举攻击者）、`pg_infer_def.py`
（`pg_infer.py` 的拷贝，仅把数据根目录改为环境变量 `PGREV_ROOT`，
`src/` 未动）。基线复现校验：`PGREV_ROOT=defense/baseline` 跑反推，
输出与 `data/sky130hd_gcd/pdn_inferred.cfg` **逐字一致**。

---

## E1：交织 decoy 网格（D3，主推）+ D1 对照

对象：sky130hd/gcd。met4 pitch = 27140 dbu、met5 pitch = 27200 dbu
（从几何实测）。

### 精确操作

- **E1a（D3）**：met4/met5 每条真 stripe 在 `+P/4` 处复制一条同宽 stripe
  （同 net），并平移复制其全部 via 栈（met1-met2/met2-met3/met3-met4 栈
  及 met4-met5 via）；另补 decoy×decoy 同网 met4-met5 via
  （忠实模拟"第二遍 pdngen"行为）。复制受 pdngen 循环界
  `center < area_max − width` 约束。结果：+36 条 decoy stripe
 （met4/met5 各 18），wire 133→169，via 2907→5994。
- **D1b（弱对照）**：同位置 decoy，但只复制 wire 行、不复制 via
  （挂网无 via）。
- **D1a（机制对照）**：悬空 decoy（无 net 归属）——`dump_pg.tcl:7-9`
  的 net 过滤使其**不可能进入**反推输入，无运行时效应；以代码审查为据，
  未跑空转实验。

### 攻击者侧（朴素 `pg_infer.py`，零修改）

| 变体 | exit | 结果 |
|---|---|---|
| E1a（D3） | 1 | `AssertionError: non-uniform pitch met4 VDD`——**崩溃**，无参数输出 |
| D1b（无 via decoy） | 1 | 同上崩溃 |
| D1b + 自适应 via 过滤（删去 36 条无 via stripe） | 0 | **精确恢复**：met4 `{1.600, 27.140, 13.570}`、met5 `{1.600, 27.200, 13.600}`、connect `{{met1 met4} {met4 met5}}`、POWER——与真值一致 |

结论：D3 使朴素反推崩溃；D1（无 via decoy）被"按有无 via 过滤"
（一行逻辑）彻底击败——**D1 作为独立防御被证伪**，如实记录。

### 自适应攻击者：子集枚举（E1a met4）

攻击者已知可能有 decoy，枚举全部子集找等差数列（容差 2 dbu）：

| net | stripe 数（真+decoy） | k=9 的有效 AP 子集 | k=10 的有效 AP 子集 |
|---|---|---|---|
| VDD | 19（10+9） | **3**（真网 2 个 9 子列 + decoy 网） | **1**（真网） |
| VSS | 18（9+9） | **2**（真网 + decoy 网） | 0 |

解读：VSS 上攻击者面对**两个完全等价**的 9 条 AP 网格——哪个是设计者
原意不可判定，这正是想要的**意图不可辨识性**。VDD 上若攻击者事先知道
原网是 10 条则唯一，但该先验正是攻击者没有的；且防守者可反转
"谁多谁少"的假设（decoy 占多数时"最大 AP 即原网"的启发式失效）。
D3 防的是朴素反推器，对知晓 decoy 存在的自适应攻击者，
其剩余价值是**组合歧义**而非不可解性——诚实标注边界。

### 防守者侧（E1a）

| 判据 | 结果 |
|---|---|
| 连通性（wire 图，类 PSM-0040） | VDD/VSS 各 **1** 连通分量；dangling via 0 |
| stripe spacing | met4 最小 5.185µm（≥ LEF 0.3µm ✓）；met5 最小 5.2µm（≥ LEF 1.6µm ✓） |
| 电阻 mesh（1A 均匀 rail 注入） | worst drop 66.90 → **25.98 mV/A（−61.2%）**，mean 38.89 → 11.63 mV/A |

D3 的物理代价是**负**的（更多并联金属 → IR 显著变好），代价只在
布线阻塞/via 数量（本实验未量化 routability 影响，列为后续工作）。

---

## E2：pitch 抖动灵敏度曲线（D2）

对象：sky130hd/gcd met4。`δ ~ Uniform(−j, +j)`，j ∈ {0, 2%, 5%, 10%, 15%} × pitch，
每档 3 种子；stripe 与其 via 栈（含 met4-met5 via 的 x 坐标）整体平移。
防守者约束：LEF min spacing（违例重采样，本次 0 次）；
via 须保持落在 rail/met5 范围内（边缘 stripe 逐条重抽 δ，15% 档共 2 次；
**教训**：首版未加该约束时，15% 档边缘 stripe 的 via 悬空导致 VDD
分裂为 2 分量——抖动的上界不止被 spacing 卡，还被 perpendicular
overlap extent 卡，已修正并如实记录）。

### 攻击者侧

| j | 朴素反推 | 鲁棒攻击者（最小二乘 pitch 拟合）pitch 相对误差 | offset 误差 |
|---|---|---|---|
| 0% | exit 0，精确（管线自检） | 0 | 0 |
| 2% | exit 1（崩溃） | 均值 0.14%，最大 0.21% | ≤ 0.38µm |
| 5% | exit 1 | 均值 0.42%，最大 0.76% | ≤ 0.71µm |
| 10% | exit 1 | 均值 0.40%，最大 0.97% | ≤ 1.63µm |
| 15% | exit 1 | 均值 0.50%，最大 1.19% | ≤ 2.97µm |

结论：朴素反推在 **j ≥ 2% 即崩溃**（容差 ±2 dbu 被远超）；
但鲁棒攻击者（~30 行最小二乘）在 15% 抖动下仍把 pitch 恢复到
**1.2% 以内**。D2 的防御效果是"降精度"而非"致盲"——这是 D2 的
诚实上限，曲线本身即论文图表。

### 防守者侧（13/13 runs）

连通性 VDD/VSS 均为 1 分量，dangling via 0；
min spacing ≥ 5.68µm（≫ 0.3µm LEF）；
mesh worst drop 相对基线变化 **±0.62% 以内**（无系统性退化，
符合"平均金属密度不变"的预期）。

---

## E3：via 稀疏化打 connect（D4，对照性质）

对象：sky130hd/gcd。rail→strap via 栈 912 个（每栈 3 via，
met1-met2/met2-met3/met3-met4），共 2736 vias。

### E3a：随机删除 p% 的 via 栈（种子 42）

| p | 删除 stacks/vias | 反推 exit | 恢复的 connect | 连通性 | mesh worst drop 变化 |
|---|---|---|---|---|---|
| 10% | 91 / 273 | 0 | `{{met1 met4} {met4 met5}}`（**不变**） | 1/1 | **+42.4%** |
| 30% | 274 / 822 | 0 | 不变 | 1/1 | **+108.1%** |
| 50% | 456 / 1368 | 0 | 不变 | 1/1 | **+425.7%** |

结论：connect 反推基于 **span 类型**（非实例），删实例不改变输出——
via 数量对推断的贡献度为零，D4 **不能独立作为防御**（预注册的负结果
得到实证）。防守者侧代价陡峭：删 50% 栈 → worst drop 恶化 4.3 倍。

### E3b：删除全部 met2-met3 via（整段 span 移除，912 vias）

- 攻击者：connect 被误判为 **`{{met4 met5}}`**（丢 `{met1 met4}`）——
  via 链断裂确实污染 connect 推断。
- 防守者：**PDN 碎裂**——VDD/VSS 各 49 个连通分量
 （48 条孤立 rail + 1 个悬空 stripe 岛）；192/192 rail 注入节点
  与馈电断开；1824 个 via 段成为死端。
  mesh 在此状态下无定义的压降（`worst_drop_V = None`，
  代码层面拒绝给出 vacuous 数字）。
- Roundtrip 投影（解析，未重跑 pdngen）：误判配置 `{{met4 met5}}`
  重跑 pdngen 将产生**零 rail→strap via 栈**（2736 vias 缺失，
  机制同 phase-5 v_conn），即"防御"把电网本身杀死了。

结论：想靠删 via 骗过 connect 反推，必须先把 PDN 弄坏——
D4 作为防御是**自杀式**的；其价值仅在于量化"connect 可辨识性
依赖于 via 链完整性"（呼应 phase-5 的证伪）。

### 实现中修正的一个建模 bug（诚实记录）

首版连通性/mesh 把 via 栈视为 bottom→top 直通边，未检查中间
span 是否连续，导致 E3b 初测"依然连通"。已修正为**连续 span 链**
语义（`lib._stack_chains`）：栈只有在 span 无缺口时才导通。
修正后 E3b 正确显示碎裂；基线/E1/E2（栈完整）结果不受影响，
已全部重跑验证。

---

## 总表：防御机制 × 效果

| 机制 | 朴素反推 | 自适应攻击者 | 物理代价 | 诚实评级 |
|---|---|---|---|---|
| D3 交织 decoy（E1a） | 崩溃 | 子集枚举 → 组合歧义（VSS 2 选 1 不可辨） | IR **−61%**（变好）；布线阻塞未量化 | 主推，有边界 |
| D1 无 via decoy | 崩溃 | via 过滤 → **精确恢复**（证伪） | 无 | 弱，仅对照 |
| D1 悬空 decoy | 无影响（抽取器过滤） | — | 布线资源 | 无效 |
| D2 抖动（E2） | j≥2% 崩溃 | LS 拟合 → pitch 误差 ≤1.2% | IR 变化 ±0.6% | 降精度，非致盲 |
| D4 via 稀疏（E3） | connect 不变（p≤50%）/ 误判（整段删） | wire 参数始终不受影响 | +42%~+426%；整段删 = PDN 碎裂 | 自杀式，仅对照 |

## 计算成本

全部实验在 2 CPU / 7.7GB VM 上分钟级完成：
E1（含 mesh）~2 min、子集枚举 ~1 s（C(19,10)=92378）、
E2（13 runs × 反推+mesh）~7 s、E3 ~2 s。
主要耗时是脚本开发与 E2/E3 的两处建模修正（均已如实记录）。

## 局限（论文必须写）

1. Mesh 是对比性一阶模型：均匀电流、理想 met5 馈电、标称 via 电阻
   5Ω、无封装/EM signoff——不能包装成"验证通过"。
2. 未量化 D3 的 routability 代价（需跑完整 flow 到 route）。
3. 载体为玩具设计（gcd）；结论外推收敛。
4. 全部基于 OpenROAD f12e2f47（2022）PdnGen.tcl；新版行为可能不同。
5. 防的是**参数/规则提取**（设计 IP），不是几何克隆（另一威胁模型）。

## 产物

- `defense/E1/`：`defense_E1_results.json`、`subset_attack.json`、
  `e1a_infer_stdout/stderr.txt`、`data/e1a_*`、`data/d1b_*`
- `defense/E2/`：`defense_E2_results.json`、`data/e2_j*_s*`
- `defense/E3/`：`defense_E3_results.json`、`data/e3a_*`、`data/e3b_*`
- `defense/baseline/`：基线复现（含 `mesh.json`）
- `defense/lib.py`、`run_e1.py`、`run_e2.py`、`run_e3.py`、
  `robust_pitch.py`、`subset_attack.py`、`pg_infer_def.py`
