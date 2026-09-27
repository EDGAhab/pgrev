# rev5 任务 C：E1 意图歧义深挖（回应审稿人"前向模型完备性"质疑）

日期 2026-09-27 PDT。对象：E1a（D3 交织 decoy，sky130hd/gcd，met4/met5 +P/4 插入 36 条带完整 via 栈 decoy stripe）。
产物几何：`defense/E1/data/e1a_sky130hd_gcd/pg_shapes.csv`（E1 原始产物未丢失，无需重做）。

审稿人主张：攻击者手握 pdngen 前向模型，可检验每个候选 stripe 子集是否为
**某个 pdngen 参数集的完整输出**，从而排除截断子序列、缩小歧义。
本任务把该主张实做为两个检验，**如实报告**（含负结果）。

## 检验 1 — 候选子集完备性（前向拟合）

### 方法

对 `subset_attack.py` 找出的 6 个候选（VDD k=9×3、VDD k=10×1、VSS k=9×2），
逐个做参数拟合：是否存在 `(offset, pitch, width)` 使前向模型输出**精确**
等于该子集几何（dbu 级逐点相等）。

前向模型 = `src/pg_infer.py::fwd_stripe_centers` 的 per-net 循环语义，
忠实复刻 `PdnGen.tcl@f12e2f47` 的 `generate_upper_metal_mesh_stripes`
（循环 `for x=offset; x < area_far − width; x += pitch`，stripe 中心即循环变量；
leading-stripe dropout trim：`center − w/2 ≥ area_edge − 1` 才保留，rev4 已验证）。
grid area 取攻击者可见的 stdcell area（met4：`ref=near=10120, far=269560 dbu`），
width 取实测 1600 dbu。offset 假设搜索 `o0 + m·p (m ∈ {−1,0,+1})`，
`o0 = sub[0] − ref`（dropout 可藏起一根前导 stripe，故含 m=−1）。

**验证**：该复刻以前向方式从真值参数精确重建两条真网 met4 网格
（VDD 10 条 o=13570/p=27140；VSS 9 条 o=27140/p=27140，逐点相等），
方法可信。未跑 live OpenROAD（Tcl 循环仅 3 行，复刻已验证；报告中如实声明）。

作用域声明：检验的是**单网 met4 wire 几何**能否为某 pdngen strap 配置的
完整输出；starts_with 相位与双网配对见检验 1b；via/connect 不在子集合法性
检验范围内（那是检验 2 的范畴）。

### Verdict 表

| # | net | k | 候选子集 | verdict | 复现它的 offset（µm） |
|---|---|---|---------|---------|----------------------|
| 1 | VDD | 9 | 真网截断 drop-last（idx 0–8） | **ILLEGAL** | —（直接 o=13.570 会多出第 10 条） |
| 2 | VDD | 9 | decoy 网格（完整 9 条） | **LEGAL** | o=20.355（另有 o=−6.785 + 前导 dropout 同解） |
| 3 | VDD | 9 | 真网截断 drop-first（idx 1–9） | **LEGAL** | o=40.710（=13.570+P） |
| 4 | VDD | 10 | 真网格（10 条，ground truth） | **LEGAL** | o=13.570（另有 o=−13.570 + 前导 dropout 同解） |
| 5 | VSS | 9 | 真网格（9 条，ground truth） | **LEGAL** | o=27.140（另有 o=0.0 + 前导 dropout 同解） |
| 6 | VSS | 9 | decoy 网格（完整 9 条） | **LEGAL** | o=33.925 |

6 → **5**：仅 #1（VDD drop-last）被排除。

### 关键诚实发现

审稿人的主张**只对了一半**：drop-last 截断确实会被前向模型排除
（同样 offset 下 pdngen 会把第 10 条也打出来，9 条子集不可能是完整输出）；
但 **drop-first 截断排除不掉**——它与"offset+P 的完整 9 条网格"前向不可区分
（#3，o=40.710 精确复现）。两套 decoy 网格本身也都是合法完整输出
（#2、#6）。另：同一几何可对应多组参数（如真网 o=13.570 与 o=−13.570+
前导 dropout 同解），参数→几何在 dropout 边界处非单射，与 rev4 结论一致。

### 检验 1b — 设计层面双网配对（补充）

真实 config 以 `starts_with=POWER` 同时生成 VDD/VSS 两网（VSS = VDD + P/2）。
对 LEGAL 候选两两配对，检验是否存在 `(o, shift=P/2)` 使前向 base 网精确
等于 VDD 候选且 other 网精确等于 VSS 候选（含 top loop bound 语义：
VDD 10 条合法配对 VSS 9 条，因 `c_9+P/2` 超 bound 本来就不会生成）：

| VDD 候选 × VSS 候选 | 一致 |
|---|---|
| 真10 × 真9（ground truth） | OK |
| decoy9 × decoy9 | OK |
| 其余 4 种配对（含 VDD drop-first-9 × 任何 VSS 候选） | 排除 |

**设计层面恰剩 2 个一致假设：全真 vs 全 decoy。**
VDD drop-first-9 虽然单网合法，但配不出任何观测到的 VSS 9 网格
（相位对不上：首条相位差为负，spacing+width ≥ 0 救不了）。
即：审稿人的完备性检验把"设计级"歧义从"6 个子集"收敛到 **2 选 1**，
但**打不破** E1 的核心结论——真设计与全 decoy 设计意图不可区分。

## 检验 2 — via 不对称性

### 方法

e1a 全部 met4×met5 **同网**交叉点（stripe 矩形相交即算交叉；
met4 全高、met5 全宽，几何上全交叉），按
(true/decoy met4)×(true/decoy met5) 分四类。
true/decoy 判定：中心与 baseline 真网中心差 ≤2 dbu 为 true，
否则为 decoy（decoy 在 +P/4 处，无歧义）。
via 存在性：存在同网 met4-met5 via 中心落在交叉点中心 ±2 dbu 内。
另测 baseline（无 decoy）真×真 via 率作参照。

### 数字

VDD（met4 10真/9 decoy，met5 9真/9 decoy；baseline 真×真 90/90）：

| 类别 | via / 交叉 | 存在率 |
|---|---|---|
| true4 × true5 | 90/90 | 100% |
| true4 × decoy5 | 90/90 | 100% |
| decoy4 × true5 | 81/81 | 100% |
| decoy4 × decoy5 | 81/81 | 100% |

VSS（met4/met5 均为 9真/9 decoy；baseline 真×真 81/81）：四类均为
**81/81 = 100%**。

 pooled（两网合计）：171/171、171/171、162/162、162/162，
**四类存在率全 100%，最大差 0——完全对称**。

（decoy4 相关类别交叉数较少是因为 VDD 第 10 条真 met4 stripe 的 decoy
被 loop bound 排除——这是已知的条数差异，不是 via 模式差异。）

### 解读

via 模式**不泄露**哪组是原始网格：decoy-met4×true-met5 与
true-met4×decoy-met5 的 via 存在率完全一致（100% vs 100%），
decoy×decoy 亦然。这是对 E1 结论的**支持而非削弱**——但须如实声明边界：
该对称性依赖于 baseline "同网交叉全打 via" 的模式（本实验中成立，
pooled 真×真 171/171）；若某设计的 pdngen 跳过部分交叉，
decoy×decoy 的独立补 via 循环可能引入不对称。本载体上无此问题。

## 结论

1. 审稿人的前向完备性检验实做后，**只剔掉 1 个候选**：6 个子集中仅
   VDD drop-last-9 判 ILLEGAL（6→5）；drop-first 截断、两套 decoy 网、
   真网全部判 LEGAL。
2. 设计层面（双网配对 + loop bound）收敛到**恰 2 个**一致假设：
   全真设计 vs 全 decoy 设计——E1 "意图不可区分" 的核心结论**成立**，
   未被实质削弱。
3. via 四类交叉存在率 100%/100%/100%/100%（pooled 171/171、171/171、
   162/162、162/162），完全对称，不泄露原网——E1 结论**不受 via 模式影响**。
4. 口径：与论文一致——D3 防的是**意图归因**（2 选 1 不可辨），
   不防几何克隆；"意图归属实际价值薄"已在论文中承认，本检验不改变该定位，
   只把"歧义到底剩几个"从文字论证变成实测数字：**子集级 5 个合法候选，
   设计级 2 个一致假设**。

## 产物与复现

- 脚本：`defense/rev5_expC.py`（stdlib only；检验 1/1b/2 一次跑完，~2 s）
- 结果 JSON：`defense/E1/rev5_expC_results.json`
- 本报告：`reports/rev5-expC-e1-ambiguity.md`
- 复现：`python3 defense/rev5_expC.py`（需 `~/pgrev` 路径；legacy env 未动）

## 局限

1. 检验 1 用 Python 复刻代替 live OpenROAD 前向跑（复刻已用真值双网验证
   逐点精确；Tcl 循环 3 行，风险低但如实声明）。
2. 检验 1 作用域为单网 met4 wire 几何；connect/via-span 链未纳入子集合法性
   判定（审稿人主张本身也只针对 stripe 子集）。
3. 检验 2 的对称性结论依赖本载体 baseline 全交叉打 via；换载体需重测。
4. 载体仍是单一 toy 设计（sky130hd/gcd），结论外推收敛（与既有局限一致）。
