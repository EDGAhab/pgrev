# rev3 WS2 — sky130hd 大规模随机配置扫描（N=800）

日期：2026-09-27 PDT · 工作目录 `~/pgrev` · 反推器 `src/pg_infer.py`（rev2 最小二乘+残差门版本）

> **数据说明（先读）：** 本报告的主体是 2026-09-27 白天完成的原始 800 组扫描
> （seed `20260927`，`~/pgrev/data/ws2_0000`…`ws2_0799` 几何目录完整保留）。
> 当晚 VM 重启导致 `/tmp/rev3/ws2/` 下的分析脚本与汇总丢失；本报告依据重建前的
> 终端记录与保留的几何目录重写，关键数字均有双重来源交叉核对。
> 另有一批 seed `20260928` 的独立复现扫描（§10）用于补充双重态分类细节——
> 它**不是**原扫描的重复（抽样范围有差异），报告中明确区分两者。

## 结论置顶

sky130hd/gcd 上 800 组随机 pdngen 配置：

- 生成成功 800/800（0 generation failures）
- 反推成功 734/800，失败 66/800
- 反推成功子集中**严格恢复**（全部参数 ≤2 dbu 且 `starts_with` 一致）732/734 = **99.73%**
- 按全部 800 组计，严格恢复 732/800 = **91.5%**
- width/pitch 两层全部 734/734 = **100%**

失败与非严格案例全部可解释（§4–§5），无"神秘失败"。主要局限是
**边界截断导致的跨层 `starts_with` 不一致**（65/66），属反推器规范问题而非几何不可辨识。

> **2026-09-27 深夜补充（§11）**：独立验证扫描（seed 7，N=630）确认：
> 审稿人字面例 `(POWER,o)/(GROUND,o+P/2)` **0/553** 几何全等（边界 stripe 打破对称）；
> dropout 阈值精确刻画为 met4 `o<w/2`、met5 `o<railw/2+w/2`（47/47 符合）；
> Class P 20/20、Class S 30/30 大规模确认。

## 1. 实验设置

| 项 | 取值 |
|---|---|
| 工艺/设计 | sky130hd / gcd（`2_5_floorplan_tapcell.odb`） |
| N | 800 |
| seed | `20260927`（Python `random.Random`） |
| met4 width | [0.5, 3.0] µm |
| met5 width | [1.6, 3.0] µm（<1.6 触发 PDN-0077 硬错误，故设下限） |
| pitch | [10, 40] µm（两层） |
| offset | [0, 40] µm（两层） |
| spacing | 50% 缺省；否则 met4 [0.2, 10]、met5 [2, ~22] µm（据保留几何反推的实际采样范围） |
| stripes_start_with | POWER/GROUND 各 50% |
| connect | 固定 `{{met1 met4} {met4 met5}}` |
| 判据 | 严格恢复 = 全部数值参数与真值差 ≤0.002 µm（2 dbu）且 `starts_with` 一致 |

管线：真值 cfg → 轻量 Tcl（`pdngen $cfg` + dump wire/via，无需 `make` 全流程）
→ `raw2shapes` → `pg_infer.py` → 参数对比。单组约 0.9 s（pdngen+dump）+ 0.08 s（infer），
2 并行，总 wall time 约 1 小时。

offset 参考点：met4 x=10.12 µm；met5 y=10.88−0.48/2=10.64 µm。

## 2. 总体结果

| 环节 | 数量 | 比例 |
|---|---|---|
| 生成配置 | 800 | — |
| generation failures | 0 | 0% |
| inference success | 734 | 91.75% |
| inference failures | 66 | 8.25% |
| 成功中 strict pass | 732 | **99.73%**（of 734） |
| 全体 strict pass | 732 | **91.5%**（of 800） |

> 诚实声明：**不得**把"成功子集 99.73%"写成"800 组 99.73%"。
> 按全体计的严格恢复率是 91.5%，差值全部来自 66 个 inference failure（§4）。

### 2.1 逐参数恢复率（734 个反推成功子集）

| 参数 | 恢复 | 比例 |
|---|---|---|
| met4/met5 width | 734/734 | **100%** |
| met4/met5 pitch | 734/734 | **100%** |
| stripes_start_with | 732/734 | 99.73% |
| met4/met5 offset | 732/734 | 99.73% |
| met4/met5 spacing | 732/734 | 99.73% |
| effective shift（派生） | 732/734 | 99.73% |

width/pitch 在全部 734 组中零误差（2 dbu 内）；2 个非严格案例（§5）丢分
全部来自 offset/spacing/`starts_with` 的等价表达，而非 width/pitch。

## 3. 双重态（reviewer duality）分类

对偶变换（§6 D1）：`(sw, o, p/2) ↔ (sw', (o+p/2) mod p, p/2)`。
在 734 个反推成功中，truth 与对偶**同时**满足"单层 stripe summary
POWER/GROUND 翻转 + half-pitch 偏移"判据（dual-eligible）的有 **173 组**。
对偶配置重跑 pdngen 后与真值几何对比（1 dbu 容差逐 stripe）：

| 类别 | 含义 | 数量（复现扫描 §10，196 eligible） |
|---|---|---|
| exact（MD5） | 逐 stripe 全等 | 0（3 位小数截断引入 ≤0.5 dbu，见 §10.1） |
| edge | 差异仅限边界 ±1 stripe（count 差 ≤1，中心对齐 2 dbu 内） | 137 |
| other（o>p wrap） | 真值 offset 超过 pitch，低端少 1–2 条 stripe | 59（全部满足 `o > p`，§3.1） |
| 实质内部差异 | —— | **0** |

*注：上表数字来自 seed 20260928 独立复现扫描（§10），原扫描的*
*分类明细随 /tmp 丢失；两批的定性结论一致——对偶差异只发生在边界，*
*从未出现内部实质差异。*

### 3.1 重要修正：D1 对偶要求 `o < p`

复现扫描发现：当真值 offset **超过 pitch**（`o > p`，本扫描 offset 范围 [0,40]
而 pitch [10,40]，约 1/3 配置会 wrap），D1 对偶**不成立**——
对偶配置在低端多出 1–2 条 stripe。

机制：pdngen 的 stripe 下标 `k` 从 0 开始，不取负值。真值 `o=32.002, p=18.302`
时，`k=0` stripe 在 42.122，而 `k=−1`（23.82 处）不存在；对偶 `o'=(o+p/2)%p=4.549`
则在 14.669/23.82 处正常放置 stripe。两者低端差 2 条。

因此 D1 对偶的成立条件是 **`o < p`（offset 不 wrap）**。原扫描的 173 dual-eligible
中 wrap 案例同样适用此结论（定性一致，定量明细丢失）。

## 4. 66 个 inference failure：全部可解释

| 原因 | 数量 | 代表 |
|---|---|---|
| 跨层 `starts_with` 不一致（MIXED） | 65 | `0082` |
| `bad spacing met4`（负 spacing 规范化） | 1 | `0245` |

### 4.1 边界截断 → MIXED（65 组）

机制：某层 offset 过小（`o < w/2`），该层首条 base stripe 中心落在 core 边界外
（或被裁剪到宽度为 0），pdngen 直接丢弃。此时该层**最低可见 stripe**的 net 标签
翻转（base 网的第一条没了，第二条——shifted 网——成了最低可见），而另一层顺序正常，
`pg_infer.py` 断言"跨层 `starts_with` 一致"失败。

代表 `0082`：met4 真值 GROUND、w=2.527、p=12.087、o=0.835、spacing=6.44。
o=0.835 < w/2=1.264，首条 GROUND stripe 被裁掉；最低可见 met4 stripe 是
VDD 19.922，随后 VSS 23.042；met5 顺序正常 → 跨层 MIXED。

这 65 组不是"几何不可辨识"——单层各自的 width/pitch/offset 仍可恢复；
是反推器的**规范选择**（要求跨层一致）过于严格。放宽为"逐层独立判定
`starts_with`"即可处理，属已知待办而非原理障碍。

对这 65 层的数学 stripe-grid 检查：generalized dual 的周期网格 65/65 等价
（§6）；但该检查是周期网格层面的，**不是**完整 wire+via MD5 round-trip，
报告中不夸大为后者。

### 4.2 `0245`：负 spacing 规范化 bug（1 组）

真值：GROUND、w=1.897、p=10.1、o=0.26，spacing=7.466（真值 spacing 合法为正）。
反推得真实 shift=9.363；但按"循环另一侧"归一化时 shift'=0.737 < width=1.897，
`spacing = shift' − width` 得出**负数**，`pg_infer.py` 抛 `bad spacing`。

这是反推器 spacing 归一化的边界 bug（未处理 shift' < width 的 wrap 情况），
真值本身合法。修复方向：当 shift' < width 时改用 shift 侧表达（或直接报
generalized-dual 等价类，见 §6）。

## 5. 两个反推成功但非严格的案例

### 5.1 `0346`：generalized-dual 等价表达（几何 round-trip MATCH）

真值 GROUND 被恢复为数学上等价的 POWER/generalized-dual 参数。
重跑 round-trip：wire+via 逐个全等（MD5 MATCH）。这是**合法的等价表达**，
不是恢复失败——几何上不可区分（§6）。

### 5.2 `0690`：legacy pdngen 小 spacing 工具 bug（非几何不等价）

反推得 generalized-dual，met4 spacing=0.204。重跑 pdngen 时 OpenROAD 报
`TypeError in method 'dbu_to_microns', argument 1 of type 'int'`。
定向测试：spacing 0.204–0.28 触发该 TypeError，0.3 及以上正常。
这是 legacy OpenROAD `f12e2f47` 的 pdngen 小-spacing 整数 bug，
**不能**误报为"几何不等价"。该配置的几何等价性因工具 crash 未能走完
round-trip，报告中明确记为 *tool crash* 而非 *mismatch*。

## 6. 等价类清单（本扫描实证）

| 类 | 定义 | 实证状态 |
|---|---|---|
| **P**（spacing 省略） | `spacing + width == pitch/2` ⟺ 省略 spacing（默认 half-pitch） | 定向 round-trip **MATCH**（§7） |
| **D1**（reviewer 对偶） | `(sw,o,p/2) ↔ (sw', (o+p/2) mod p, p/2)`，**要求 `o < p`** | 大规模分类：`o<p` 时差异仅限边界 ±1 stripe；`o>p` 时对偶多 1–2 条低端 stripe（§3.1）；定向 exact 切片在 1 dbu 内成立（§7） |
| **S**（DBU snap） | 参数差 <1 dbu → 几何全等 | 3 对 0.4 dbu 定向碰撞 **COLLIDE**（§7）；40 组 4 位小数随机配置零意外碰撞 |
| **T**（offset 平移） | `(sw,o)` vs `(sw,o+p)` | **证伪**：有限 core 下差恰好 1 条边界 stripe（§7），不是等价类 |
| generalized dual | flip start + `o'=(o+s) mod P` + `s'=P−s` | 65 MIXED 层周期网格 65/65 等价；`s' < width` 时**无法**用当前 pdngen 正-spacing 语法表达（§5.2） |

### 6.1 关于单射性措辞

Phase 5 曾写"参数→几何映射基本单射"。本扫描修正为：
**在"边界无截断、spacing 合法、DBU 量化"三者限定的等价类意义下可辨识**。
非平凡等价类只有 P（语法糖）与 D1/dual（边界 ±1 stripe）；T 被证伪；S 是量化本性。
论文中"empirically identifiable"的限定语必须带上这三条。

## 7. 定向验证（targeted demos）

| 实验 | 构造 | 结果 |
|---|---|---|
| Class P | `(GROUND, o=5, sp=8, w=2, p=20)` vs 省略 spacing | **MATCH**（MD5 全等） |
| Class T | `(POWER, o=0.3)` vs `(POWER, o=20.3=o+p)` | **DIFFER**：met4/VSS 差 1 条低边界 stripe（13 vs 12；20.42 处多一条），其余层/网全等 |
| Class D1 exact 切片 | `(POWER, o=13.323, p=25.939, w=2.863)` vs `(GROUND, o2=0.3535)` | 1 dbu 内成立（met4/VSS 首中心 36.412 vs 36.413；差来自 3/4 位小数截断，非几何实质） |
| Class S 碰撞 | 3 对参数差 0.4 dbu（offset/width/pitch 各一对） | **全部 COLLIDE**（MD5 全等） |
| S 取整规则 | `o=12.8056` vs `12.8064` | COLLIDE → pdngen 按** round**（非截断）到 dbu |
| S 取整细节 | width 映射抽查 | 近似 round-half-even，但 x.5 边界有 float 伪影（如 2.863→2862）；报告**不**声称已完全逆向取整规则 |

D1 切片的 1 dbu 残差值得展开：真值 VSS 首 stripe 中心 36.4125 µm = 36412.5 dbu，
恰落在取整边界上；真值侧与对偶侧的浮点求和路径不同导致取整方向差 1 dbu。
这是**表示精度**问题，不是等价类本身的问题——实数运算下 D1 exact 成立。

## 8. Round-trip 方法说明

判据：反推配置重跑 pdngen → wire 矩形（1 dbu 容差）+ via 集合逐个全等，
以 MD5（排序后坐标+层+网）为判据。`0346` PASS；`0690` 因工具 crash 未完成
（§5.2）；其余 732 strict 组按构造即 round-trip 一致（反推参数在 2 dbu 内，
pdngen 取整到 dbu 后几何一致——Class S 保证）。

*注：原扫描曾对全部 strict 组跑完整 MD5 round-trip（结论一致），明细随 /tmp 丢失；*
*本报告保留判据与抽查结论，不虚构已丢失的逐组数字。*

## 9. 局限与未做事项（诚实清单）

- **L1** 仅 sky130hd/gcd 一种设计；nangate45/asap7 未扫。
- **L2** connect 固定 `{{met1 met4} {met4 met5}}`；ring/macro 不在扫描内（WS3 另行覆盖）。
- **L3** 65 MIXED 组未做"逐层独立 starts_with"的反推器修复验证（待办）。
- **L4** `0245` 的负 spacing 规范化 bug 未修复（待办）。
- **L5** DBU 取整规则未完全逆向（x.5 边界有 float 伪影）；infer 的 2 dbu 容差覆盖了它，
但论文中不得声称"精确复现 pdngen 取整"。
- **L6** 本报告是灾后重建（/tmp 丢失）；§3 双重态分类明细与 §8 逐组 round-trip 明细
引自复现扫描或抽查，已逐处标注，不得与原扫描数字混淆。

## 10. 独立复现扫描（seed 20260928，N=800）

为补充双重态分类细节（原扫描明细随 /tmp 丢失），另跑一批独立复现扫描。
**注意：它不是原扫描的重复**——seed 不同（20260928 vs 20260927），且 spacing
抽样范围更窄（[2,10] vs 原 [0.2,~22]），故 MIXED/dropout 案例更少。报告中两者严格区分。

| 环节 | 复现扫描 | 原扫描 |
|---|---|---|
| seed | 20260928 | 20260927 |
| generation failures | 0/800 | 0/800 |
| inference success | 760/800 | 734/800 |
| inference failures | 40/800（39 MIXED + 1 bad spacing） | 66/800（65 MIXED + 1 bad spacing） |
| 成功中 strict | 758/760 = **99.74%** | 732/734 = **99.73%** |
| 全体 strict | 758/800 = 94.75% | 732/800 = 91.5% |
| width/pitch | 760/760 = 100% | 734/734 = 100% |

核心结论**定量一致**：成功子集的严格恢复率 99.74% vs 99.73%，width/pitch 零误差，
失败原因分布相同（MIXED 主导 + 1 例 bad spacing）。

### 10.1 双重态分类（复现扫描，196 dual-eligible）

| 类别 | 数量 | 说明 |
|---|---|---|
| edge（边界 ±1 stripe） | 137 | count 差 ≤1，中心对齐 2 dbu 内 |
| other（o>p wrap） | 59 | **全部**满足真值 `o > p`（§3.1 机制） |
| 实质内部差异 | 0 | —— |

MD5 bit-exact 为 0——非理论失败，而是对偶 offset `o'=(o+p/2)%p` 取 3 位小数
引入 ≤0.5 dbu 截断误差，恰好落在 pdngen 取整边界上时差 1 dbu（§7 D1 切片有实例）。

### 10.2 两个非严格案例（`0672`、`0676`）

均为 generalized-dual 等价表达（`starts_with` 翻转 + offset/shift 重参数化），
width/pitch 全对。复现了原扫描 `0346` 的现象——反推器输出合法等价参数，
非恢复失败。

---

## 附录：可复现性信息

- OpenROAD `f12e2f47`，ORFS `96eb3de`（legacy 工具链，不升级）
- 反推器：`~/pgrev/src/pg_infer.py`（rev2 最小二乘+残差门）
- 原扫描几何：`~/pgrev/data/ws2_0000`…`ws2_0799`（gitignored，大文件未进 repo）
- 本报告：`~/pgrev/reports/rev3-ws2-randscan.md`（唯一进 git 的文件）
- 复现脚本：scratch，已按用户要求清理，不进 repo

---

## 11. 独立验证扫描（seed 7，N=630，2026-09-27 深夜）

为直接验证审稿人字面例（`§3` 的 D1 是 `(o+p/2) mod p` 形式，此处测**不取模**的字面形式），
并精确刻画 dropout 阈值，另跑一批独立扫描。**不是**原扫描的重复——seed 不同（7），
offset 范围为 `[0, 1.2×pitch]`（偶数 dbu），且每个配置附带对偶几何全等测试。

| 环节 | 数量 |
|---|---|
| primary 配置 | 600 |
| dbu-exact 恢复（全部参数） | 553/600 = **92.2%** |
| infer_fail（全部为 §11.1 dropout） | 47/600 = 7.8% |
| 定向 spacing (`s+w==p/2`) → equiv，round-trip PASS | 20/20 |
| 高 pitch（150–300 µm）exact / unidentifiable / crash | 1 / 6 / 3 |
| 分数 dbu 对（±0.35 dbu）几何全等 | 30/30 |
| 审稿人字面对偶 `(¬sw, o+shift)` 几何全等 | **0/553** |

单配置平均 4.1 s（含真值+对偶两次 pdngen、两次 extract、infer），2 workers 总计约 45 分钟。

### 11.1 Dropout 阈值的精确刻画

47/47 的 `MIXED!` 崩溃符合以下规则（无一例外）：

- **pdngen 丢弃未完全落入 core 的 stripe**（下边缘 `< core_min` 即丢弃）：
  - met4（垂直）：`offset < width/2`；
  - met5（水平）：`offset < rail_width/2 + width/2`（因 `ref_y = core_y1 − railw/2` 在 core 之下）。

阈值经二分实测：met4 在 `o=0.5µm`（下边缘 9820 < 10120）丢弃、`o=0.8µm`（下边缘恰为 10120）保留；
met5 在中心 11430 dbu 丢弃、11440 dbu 保留（10 dbu 窗口）。

这是推断器的建模缺口（未建模掉落），非根本不可辨识——给定掉落规则，真值仍是唯一全局配置。

### 11.2 审稿人字面对偶的直接证伪（0/553）

对 553 个 exact 配置逐一生成字面对偶 `(starts_with 翻转，offset += shift)` 并跑 `pdngen` 对比几何：
**0 组全等**。手工解剖一例（`(POWER,o=5µm)` vs `(GROUND,o=15µm)`）：相差 2 条 wire + 169 个 via，
差异恰为 `ref+o` 处的边界 stripe——`(POWER,o)` 恒在 core 边缘内放置该 stripe（`o≥0` 时），
对偶的 VDD 网格平移 `P` 后丢失它。

**结论**：`o≥0` 时审稿人字面例不构成等价类；`starts_with` 与 `offset` 联合可辨识。
（`§3` 的 D1 是取模形式，另见 §3.1 的 `o<p` 条件；两者一致——边界决定一切。）

### 11.3 其他

- **Class P 大规模确认**：20/20 的 `spacing+width==pitch/2` 配置被推断器规范化为省略 spacing 形式，round-trip 20/20 PASS。
- **Class S 大规模确认**：30 对 ±0.35 dbu 分数变体几何 30/30 全等。
- **pdngen 输入验证**：`spacing < min_width` 时报 `TypeError in method 'dbu_to_microns'`（非正常 PDN 错误），
  系错误报告路径的 SWIG bug；`width < min_width` 报正常的 `PDN-0077`。采样时已据此约束（met4 `w≥0.4µm/s≥0.3µm`，met5 `w≥1.6µm/s≥1.6µm`）。
- **高 pitch**：单 stripe/网时 pitch 确不可辨识；推断器在部分层可辨识时正确省略（6 组），全不可辨识时崩溃（3 组，`starts_with` 为 None 触发同一断言）。

本批 driver：`/tmp/rs/scan.py`（seed=7），结果 JSON `/tmp/rs/results/`（630 个），`frac_test.py`（seed=42）。
/tmp 为 512MB tmpfs，扫描中途曾写满致 520 个结果损坏，已清理 work 目录并重跑补齐——最终 630/630 有效。
