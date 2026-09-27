# rev4 实验 A：dropout-aware 重扫（N=800 全量恢复）

日期 2026-09-27 PDT。目标：给 `src/pg_infer.py` 加 dropout-aware 前向验证/修正循环，
把 rev3 WS2 随机扫描（N=800，seed 20260927）中 66 个 inference failure 全部恢复，
回归原 4 设计 + WS1/WS3 不受影响。

## 1. 结论一句话

- **inference 成功率**：734/800 → **800/800（100%）**；66 个原失败案例全部可 infer。
- **几何 round-trip**：800/800 全过（含 66 个新恢复案例的 bit-exact wire/via 全集对比）。
- **参数严格恢复**：732/800（91.5%）→ **796/800（99.5%）**；剩余 4/800 为 genuine 几何等价（equiv），0 失败。
- **回归**：4 baseline 设计 + WS1 输出 byte-identical 且 round-trip 全 PASS；WS3 脚本未改动、编译通过。

## 2. 方法：仅失败时触发的修正循环

正常路径（naïve 最小二乘 + 残差门）**完全不动**。仅当 naïve 因
`starts_with` 不一致（MIXED）或 bad spacing 抛异常时，进入 dropout-aware 修正：

1. **前向模型** `fwd_stripe_centers(ref, near, far, o, pitch, width, shift)`：
   精确复刻 `PdnGen.tcl` 的 stripe 生成（含 leading-stripe dropout 语义
   `center − width/2 < near − 1` 时丢弃），整数 DBU 运算。
2. **假设搜索** `infer_layer_dropout`：枚举 `(base_net, k)`，
   k = 被丢弃的 base-grid 前导 stripe 数；offset 候选
   `o = 首个可见 base stripe 中心 − k·pitch − ref`；
   每个候选过前向模型全几何验证（两网全部 stripe 中心/数量 + 顶部循环边界）。
3. **跨层一致**：枚举**全部**全局一致的 `(starts_with, 每层选择)` 组合；
   若 >1 个，输出 `AMBIGUOUS` NOTE（见 §5），按确定性 tie-break 选择。
4. **default-vs-explicit spacing 精确判定**（整数 DBU，见 §4）。

修正分支的输出带 `# NOTE:` 说明触发原因、base net、k、前向验证通过情况。

## 3. 关键 bug 修正：1-DBU spacing 误判（ws2_0082）

首轮 66 个 round-trip 中 65 PASS、仅 `ws2_0082` FAIL。
根因：修正分支曾用容差判断 default spacing——观测 shift=7469 dbu，
Tcl 默认 `pitch//2`=7468 dbu，容差把它误判为"默认半 pitch"而省略 explicit spacing，
导致另一网全部 stripe 偏移 1 dbu（半整数截断）。

修正：default-vs-explicit 必须**精确**判定——仅当 `shift == pitch//2`
（整数）时省略 spacing，否则输出 `spacing = shift − width`。
修正后 `ws2_0082` round-trip bit-exact。教训：PDN 参数里 1 dbu
也不是"噪声"，容差只能用在"观测 vs 预测"的验证侧，不能用在"参数取舍"侧。

## 4. 实证修正：met5 dropout 阈值

定向 Tcl 二分实验（met5 width=2.000µm，rail width=0.480µm）：
offset 0.900µm 首条 dropout；1.000–1.300µm 首条保留。
以 `ref_y = core_y1 − rail_width/2` 为参考时，阈值是 **`offset < width/2`**，
不是 rev3 报告 §11.1 文字写的 `railw/2 + width/2`
（该节文字与其 11430/11440 dbu 实测自相矛盾，数字实际支持 `width/2`）。
本实现采用 `width/2`。

## 5. 结果：66 个原失败案例的归类

| 类别 | 数量 | 说明 |
|---|---|---|
| 参数唯一恢复（exact） | 64 | 全局一致假设唯一 → 必为真值（§6 论证）；round-trip bit-exact |
|  genuine 几何等价（equiv） | 2 | `ws2_0082`、`ws2_0507`：各有 2 个全局一致假设，几何全同但参数不同 |
| 仍失败 | 0 | — |

66 个的 dropout 模式（每组恰一层 k=1、另一层 k=0，即 MIXED 的来源）：

| met4 | met5 | 数量 |
|---|---|---|
| base VDD, k=0 | base VDD, k=1 | 16 |
| base VDD, k=1 | base VDD, k=0 | 16 |
| base VSS, k=0 | base VSS, k=1 | 19 |
| base VSS, k=1 | base VSS, k=0 | 15 |

触发原因：65× `inconsistent starts_with across layers`，1× `bad spacing met4`。

### 5.1 两个 equiv 的性质（逐一归类）

- **`ws2_0082`**：`(POWER: met4 (VDD,k=1,o=9.802µm,s=0.594µm), met5 (VDD,k=0))`
  vs `(GROUND: met4 (VSS,k=0,…), met5 (VSS,k=1,…))` ——
  两组参数生成**逐 dbu 相同**的几何。手工构造的 GROUND 配置与当前 POWER 配置互为对偶。
  这是 dropout 引入的命名对称性：首 stripe 被丢弃后，"谁是 base 网"不可辨。
- **`ws2_0507`**：同类对偶（met5 pitch 32.128µm 高 pitch，k=1，VDD vs VSS 两解）。
  均已在输出中标 `AMBIGUOUS` NOTE。

### 5.2 一个被排除的隐藏对偶

`(k, o)` 与 `(k+1, o−pitch)` 在 `o−pitch ∈ [0, width/2)` 时几何全同
（wrap 对偶）。实现中**不**提前 `break` 取最小 k，而是保留全部验证通过的 k、
计入全局枚举。66 个案例中该对偶**一次未出现**（AMBIGUOUS 仍为 2 个），
故 64 个"唯一"结论不受此影响。

### 5.3 高 pitch / 根本不可辨识

- 单网单 stripe（pitch 不可辨识）分支在 N=800 中**未触发**（全部 800 均有多 stripe）。
- 本次扫描**无剩余失败**；"根本不可辨识"仅体现为上述 2 个 genuine 几何对偶
  （参数不可辨，几何可辨——round-trip 仍 bit-exact）。
- 另有 rev3 原 734 个成功输出中的 2 个 equiv（rev3 按 ≤2dbu 判 strict，
  732 exact；原始逐项结果已随 /tmp 丢失，未能重新定位是哪 2 个，如实记录）。

## 6. "64 个唯一 ⇒ 必为真值"的论证

1. 前向模型逐 dbu 复刻 Tcl（多案例验证 + 800/800 round-trip 佐证），
   真值的 `(base_net, k=j0)` 假设必在枚举范围内（kmax 覆盖）且必通过验证。
2. 因此真值必是"全局一致假设"之一；当全局一致假设唯一时，它只能是真值。
3. 64 个案例均为唯一 → 参数精确恢复（比 rev3 的 ≤2dbu 更强：是唯一性）。

## 7. 回归

| 对象 | infer 输出 | round-trip |
|---|---|---|
| sky130hd_gcd（133 wires） | byte-identical | PASS |
| nangate45_gcd（65 wires） | byte-identical | PASS |
| sky130hd_aes（318 wires） | byte-identical | PASS |
| asap7_gcd（114 wires） | byte-identical | PASS |
| WS1 sky130hd_gcd_unlabeled（133 wires） | byte-identical | PASS |
| WS3 ring/macro | 脚本未改动（`git status` 仅 `src/pg_infer.py` 被修改），`py_compile` 通过 | — |

- 734 个原 ws2 成功输出：新 inferrer 重跑**全部 byte-identical**（734/734），
  确认修正分支未触及正常路径。
- WS3 说明：ring/macro 用独立脚本（`pg_infer_ring.py`/`pg_infer_macro.py`），
  本次未修改；其 scratch 数据（`/tmp/rev3/ws3`）已随 /tmp 丢失，
  未重做完整 round-trip，如实注明。脚本本身不受本次改动影响。

## 8. 恢复率总表

| | rev3 | rev4（本实验） |
|---|---|---|
| inference 成功 | 734/800 (91.75%) | **800/800 (100%)** |
| 几何 round-trip 通过 | 734/800 | **800/800** |
| 参数严格恢复（exact） | 732/800 (91.5%) | **796/800 (99.5%)** |
| 几何等价（equiv，参数不可辨） | 2/800 | 4/800（2 原有 + 0082/0507） |
| 失败 | 66/800 | **0** |

## 9. 局限与后续

1. 原 N=800 truth JSON 已随 /tmp 丢失；64 个"exact"依赖 §6 的唯一性论证，
   而非与 truth 的逐项比对。论证是可靠的（前向模型 sound + 枚举完备），
   但论文中应如实说明验证方式。
2. 修正分支的时间复杂度为 O(kmax)，kmax 与 offset/pitch 比值成正比；
   本次扫描最大 k=1，无性能问题。极端高 offset 采样下可加剪枝。
3. `AMBIGUOUS` 的 tie-break（POWER 优先）是确定性的，但选择本身无信息量；
   下游若需无偏，应消费 NOTE 而不是默认输出。
4. WS3 未重做完整 round-trip（scratch 丢失）；若论文引用，需重跑或注明。

## 附：改动文件

- `src/pg_infer.py`（唯一修改的 tracked 文件，+265/−14）：
  `fwd_stripe_centers`、`fwd_validates`、`infer_layer_dropout`、
  全局一致枚举 + AMBIGUOUS NOTE、整数精确 spacing 判定。
- 本报告 `reports/rev4-exp1-dropout-rescan.md`。
