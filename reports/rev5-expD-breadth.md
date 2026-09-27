# rev5 实验 D：广度扩展扫描（回应审稿人第 3 点"评估广度不足"）

日期 2026-09-27 PDT。目标：把 rev3 WS2 / rev5 expA 的随机扫描从
"sky130hd/gcd、只随机化 stripe 参数" 扩展到**多 PDK、多层选择、
大尺寸设计**，验证 dropout-aware 推断器（冻结的 `src/pg_infer.py`）
的跨工艺鲁棒性。

## 1. 方法

管线与 rev5 expA 同构（`src/randscan_breadth.py` 新写，复用
`randscan.py` 的 worker 结构，配置模板/层名/DBU/采样范围按设计参数化）：

真值 cfg → `pdngen`（`/tmp/rsB/run_pdn.tcl`，`read_db → pdngen → write_db`）
→ export DEF + dump wire/via → `pg_extract.py` → `pg_infer.py`
→ 通用 dbu-精确对照（sw / rail 宽 / 每层 strap w-p-o-s / **connect 对集合**）
→ **所有可推断组实测 round-trip**（重跑 pdngen，`pd_diff.py` 比 wire/via 全集）
→ dual-config 对偶检验（小设计；aes 跳过以省时间）。

真值 JSON 全部进 repo：`reports/rev5-breadth-truth/<design>/cfg_%04d.json`
+ `MANIFEST.json`（seed、采样器标识、git commit），**严禁 /tmp**
（结果明细 JSON 在 `/tmp/rsB/results/`，三指标固化于本报告）。

三指标定义（与 expA 一致，判据为整数 dbu 全等，严于 ≤2dbu）：
- **inference success**：推断器产出配置（status ∈ {exact, equiv, unidentifiable}）；
- **round-trip pass**：重跑 pdngen 后 wire/via 全集一致（全部实测）；
- **exact**：参数逐项 dbu 全等 + starts_with 一致 + round-trip 通过。

### 1.1 三套扫描的采样维度

| 扫描 | N | seed | 随机化维度 |
|---|---|---|---|
| nangate45/gcd | 300 | 20260930 | stripe w/p/o/s/sw + **connect 对** + rail width + **strap 层选择**（L1∈{metal2,metal4,metal6}，L2 为其上反向层） |
| asap7/gcd | 300 | 20261001 | 同上；L1∈{M3,M5}，L2 为其上反向层；**双 rail 层 M1/M2**（phase-4 已验证启发式支持） |
| sky130hd/aes | 200 | 20261002 | 尺寸 scaling：与主扫描同采样器（met4/met5），floorplan 为 aes（~11k–25k shapes/组，主扫描 gcd 为 ~1k 量级） |

层名/DBU/最小宽度按各 PDK tech LEF 取值：
- nangate45：DBU=2000，层名 metal1–metal7；min width metal1/2/3=140dbu，
  metal4/5/6=280dbu，metal7=800dbu；pitch∈[8000,30000]dbu；
  rail width∈{340,680,1020,1360}dbu。
- asap7：DBU=1000，层名 M1–M7；min width M1/2/3=18，M4/5=24，M6/7=32dbu；
  pitch∈[1200,3600]dbu（core 仅 14040dbu 见方）；rail width∈{18,36,54,72}dbu。
- sky130hd/aes：DBU=1000，met4/met5；pitch∈[8000,50000]dbu；
  rail width∈{240,480,720,960}dbu（与主扫描一致）。

connect 恒为规范链 `rail[0] → L1 → L2`（即推断器 via-span collapse
恢复的规范形；phase-5 已证明高跨单对与拆分对不等价，故不采样病态形式）。

### 1.2 "合法层选择"约束（pilot 发现，见 §4）

采样约束：**L1 取垂直层（⊥水平 rail），L2 取 L1 之上的反向层**
（交替方向，与所有真实 PDN 网格一致）。
pilot 证实：平行于 rail 的 strap 层（如 nangate45 metal3(H) vs metal1(H)
rail、asap7 M4(H) vs M1/M2 rail——注意 asap7 的 M1/M2 rail 均为 FOLLOWPIN
沿水平 row 走，与 LEF 首选方向无关）与 rail 无交叉→其 rail→strap
connect 对产生 0 via→几何死参数（推断 connect 自动丢弃该对，
round-trip 仍 bit-exact）。此类构形是**断开的 PDN**（strap 悬空），
属非真实设计，排除在采样之外；约束本身在报告中明确声明。

### 1.3 性能说明（回应任务书的 O(V²) 警告）

WS1 报告的 via-via 双重循环 O(V²) 位于 `src/expB_unlabeled.py`
（无标签攻击），**本扫描的主流水线（pdngen→extract→pg_infer→pd_diff）
不含该循环**：`pd_diff.py` 用 Counter 比集合为 O(V)。
aes pilot（n=3，11k–25k shapes/组，16403 vias 量级）平均 8.0 s/组，
无需空间索引即可全量。

## 2. 结果

三套扫描全部完成（2026-09-27 PDT；中途 VM 重启一次，/tmp 结果被清空，
nangate45/asap7 的三指标摘要以重启前日志为准、真值在 repo 不受影响；
aes 用同一种子确定性重跑 200 组，真值覆写一致）。

| 扫描 | N | inference success | round-trip pass | exact | 非 exact 明细 |
|---|---|---|---|---|---|
| nangate45/gcd | 300 | 299/300 (99.7%) | 299/300 | 299/300 | 1 fail（cfg 0046） |
| asap7/gcd | 300 | 298/300 (99.3%) | 298/300 | 297/300 (99.0%) | 2 fail（cfg 0004, 0160）+ 1 equiv（cfg 0161） |
| sky130hd/aes | 200 | 200/200 (100%) | 200/200 | 198/200 (99.0%) | 2 equiv（cfg 0077, 0186） |
| **合计** | **800** | **797/800 (99.6%)** | **797/800** | **794/800 (99.25%)** | 3 fail + 3 equiv |

辅助统计：
- nangate45：dropout engaged 34/300（11.3%），avg wall 3.9 s/组；
  层组合分布 (metal4,metal7):56，(metal6,metal7):86，(metal4,metal5):55，
  (metal2,metal3):35，(metal2,metal7):40，(metal2,metal5):28；
  sw GROUND:158 / POWER:142。
- asap7：dropout engaged 29/300（9.7%），avg wall 3.7 s/组。
- aes：dropout engaged 17/200（8.5%），avg wall 8.7 s/组；
  dual-config 对偶检验未做（省时间）。

结论：冻结的 dropout-aware 推断器在**三个 PDK、6 种 strap 层组合、
双 rail（asap7 M1/M2）、大尺寸 aes** 上保持 ~99%+ 的严格恢复率；
全部 3 个 fail 与 3 个 equiv 均有明确归因（§4），无"原因不明"项。

## 3. 与主扫描（rev5 expA，sky130hd/gcd N=800）对比

| 指标 | expA（sky130hd/gcd, N=800） | expD 本实验（三 PDK, N=800） |
|---|---|---|
| inference success | 800/800 (100%) | 797/800 (99.6%) |
| round-trip pass | 800/800 (100%) | 797/800 (99.6%) |
| exact | 798/800 (99.75%) | 794/800 (99.25%) |
| 非 exact | 2 equiv（genuine 对偶） | 3 fail + 3 equiv |

差异全部来自一类**新失败模式**（§4.1–4.2）：pdngen 内部以浮点
micron 求值、整数 dbu 真值参数可能产生与精确整数运算差 1–2 dbu
的观测几何；推断器（整数 dbu 运算）据此锁定一个差 1–2 dbu 的参数化，
被严格 round-trip 捕获。sky130hd 的 1000 组（expA 800 + 本实验 aes 200）
中该模式出现 0 次，nangate45/asap7 的 600 组中出现 3 次——机制是
PDK 无关的（pdngen 的 um 求值），但细粒度 dbu 下是否更高发需更大样本，
此处不断言 PDK 效应。

## 4. 失败/非 exact 归因

### 4.1 新失败模式 A：AMBIGUOUS 对偶分支差 1 dbu（nangate45 cfg 0046，
status=fail）

真值 sw=GROUND，metal5 {w:1278, p:28034, o:246, s:None}；
推断 sw=POWER，metal5 {w:1278, p:28034, o:14262, s:None}，
metal2 重参数化 {o:13378,s:2112}→{o:1780,s:7580}。
推断器报 AMBIGUOUS（2 个全局一致假设），确定性 tie-break 选 POWER。

手动重跑验证（真值 cfg vs 推断 cfg 各跑一次 pdngen，dump 对比）：
- metal2 的 VDD/VSS 条带**逐个全等**（wrap 对偶的重参数化，几何精确）；
- metal5 的 5 条 VSS 条带**系统性偏 −1 dbu**
  （如 TRUTH (162007,163285) vs INF (162006,163284)，5 条皆然）；
- metal5 的 VDD 条带同样差 1 dbu（共 11 条线网矩形不一致，
  与 rt_detail 的 only_in_orig=11/only_in_rt=11 吻合）。

机制：真值的 VDD（other net）中心在 um 浮点求值下落在整数 dbu
边界（如 18.2465um→36492.999…→截断为 36492 而非 36493），
观测几何据此导出 o=14262 而非 14263；两个 AMBIGUOUS 分支因此
**不是 bit-exact 而是差 1 dbu**，推断器的 2-dbu 前向验证门放行了
错分支，严格 round-trip（pd_diff 经 banker's rounding 能捕获 1-dbu）
将其拒绝。这是 genuine 的近对偶，不是推断器 bug；
改进方向（未做，推断器冻结）：对 AMBIGUOUS 的全部分支实测
round-trip，选 bit-exact 者。

### 4.2 新失败模式 B：spacing 在 p//2 边界被坍缩为默认
（asap7 cfg 0004、cfg 0160，status=fail）

- cfg 0004：真值 M5 {w:312, p:1266, o:492, s:320}（shift=632，
  p//2=633）；观测 shift 恰为 633=p//2，推断器的精确相等规则
  `shift == pitch//2 → spacing=None` 把显式 spacing 坍缩为默认；
  重跑后 VSS M5 条带差 1 dbu → rt fail（5 条）。
- cfg 0160：真值 M6 {w:232, p:1220, o:940, s:380}（shift=612，
  p//2=610）；观测 shift 恰为 610，同样坍缩；重跑后 VDD M6
  条带差 2 dbu → rt fail（11 条）。

根因同 §4.1：真值 shift 与 p//2 仅差 1–2 dbu 时，pdngen 的 um
浮点求值可使**观测 shift 恰好等于 p//2**，推断器按注释既定规则
（`pg_infer.py`："观测 shift 等于 pitch//2 时与显式
spacing+width==pitch//2 不可区分，输出默认可精确复现"）
输出默认；但此处真值并非 p//2±0 而是 ±1–2，重跑的浮点求值顺序
不同，落到差 1–2 dbu 的另一侧。判据本身在"观测恰等于 p//2"
时是正确的——错的是观测，不是规则；这是 pdngen 浮点求值与
整数 dbu 真值之间的 1-dbu 裂缝。

### 4.3 genuine 对偶（equiv，rt 通过；非失败，计入 success）

- asap7 cfg 0161：经典 AMBIGUOUS（sw GROUND→POWER，
  M3/M6 offset 重参数化），round-trip bit-exact。
  与 expA 的 cfg 0462 同类。
- aes cfg 0077：AMBIGUOUS（sw 翻转 + met4/met5 offset/spacing
  重参数化），rt 通过。
- aes cfg 0186：AMBIGUOUS（sw GROUND→POWER，
  met4/met5 offset 重参数化），rt 通过。

三例均为几何上**真正不可区分**的参数对（Z2 命名对称 + wrap
对偶的复合），推断器按"几何往返一致"的主判据应判 equiv；
与 expA 的 2 例一起，对偶率约 5/1600（0.3%）。

### 4.4 PDK 特有模式小结

- **nangate45**：唯一的 fail 是 §4.1 的 1-dbu AMBIGUOUS 分支；
  其余 299 组全 exact。双层 strap 的 6 种层组合全部覆盖且无偏斜。
- **asap7**：2 个 fail 均为 §4.2 的 spacing 边界坍缩；
  双 rail（M1/M2）启发式 300/300 正确（connect 恒恢复为
  rail[0]→L1→L2 规范链，无一丢失）；1 个 genuine equiv。
- **sky130hd/aes**：200/200 success+rt；2 个 genuine equiv；
  大尺寸（11k–25k shapes）下性能线性可接受（8.7 s/组），
  O(V²) 警告不适用于本流水线（§1.3）。
- 3 个 fail 的共同根因是 pdngen 的 um 浮点求值 vs 整数 dbu
  真值的 1–2 dbu 裂缝（§4.1–4.2），**机制 PDK 无关**；
  在 sky130hd 的 1000 组中出现 0 次，本实验 600 组中 3 次，
  是否与 dbu 粒度相关需更大样本，本报告不断言。

（pilot 阶段的"平行层死 connect 对"已通过 §1.2 采样约束排除，
不计入失败；属实验设计修正，非推断器问题。）

## 5. 未覆盖声明

- **ibex / jpeg / ariane 全综合**：太重，未做。当前覆盖止于 gcd/aes
  级别的人工 floorplan（2_5_floorplan_tapcell.odb）。
- asap7 的 M7 作为 strap 顶层未被采样（交替方向约束下 L1∈{M3,M5}
  时其上无反向层）；nangate45 的 metal3(H)/metal5(H)/metal7(H) 只作为
  L2 出现、从不作为 L1（L1 恒为垂直层）。
- 单 strap 层 / 三 strap 层堆叠未采样（均为 2 层）。
- directed_spacing / high_pitch 定向探针未包含（三套均为 primary 采样；
  高 pitch 退化边界仍以 rev3 seed-7 扫描为准）。
- aes 未做 dual-config 对偶检验（省时间；两套小设计做了）。
