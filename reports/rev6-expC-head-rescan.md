# rev6 实验 C：C++ pdngen（HEAD）随机扫描 N=200 + E2 抖动防御复现

日期：2026-09-28（UTC）｜ seed `20260930` ｜ 状态：**全部完成**

## 1. 目标

- 在当前 C++ pdngen HEAD 上复现 rev5 的随机扫描三指标
（inference success / measured round-trip pass / exact parameter recovery）。
- 在 HEAD 几何上复现 E2 jitter 防御实验（naive 崩溃 + robust 最小二乘 + defender 三检查）。
- 与 Tcl 版结果对照，给出诚实边界。

## 2. HEAD 工具链与 API 迁移验证

- OpenROAD commit：`80c6be93c28244f9f72840852a667daef764a4ff`
- binary：`phase7/openroad-src/build/bin/openroad`
- 设计：`phase7/data/sky130hd_gcd_clean/floorplan.def`（sky130hd/gcd）
- legacy dict API 在 HEAD 上**直接验证不接受**：
`pdngen $PDN_CFG` → `[ERROR STA-0562] pdngen -grid {name grid} -voltage_domains CORE is not a known keyword or flag.`
（2026-09-28 实测，`/tmp/t_legacydict.tcl`）。
- HEAD 实验使用新 API：`define_pdn_grid` / `add_pdn_stripe` / `add_pdn_connect`，
最后调用无参数的 `pdngen`。最小适配脚本见 `phase7/randscan_head.py::write_gen_tcl`。

## 3. 采样器：legacy 范围 + HEAD 有效性约束（admissibility）

采样范围沿用 legacy `src/randscan.py`（pitch 8–50µm 步长 10dbu 等），
但 HEAD 有四个硬约束，违反即报错或静默删 stripe，**不能**直接沿用 legacy 域。
以下约束均经 2026-09-28 实测确立（pilot 约 34 组探索性配置，不计入最终指标）：

| # | 约束 | 证据 | 采样器适配 |
|---|------|------|-----------|
| 1 | width/pitch/offset/spacing 必须落在 0.005µm（5dbu）制造网格 | `[ERROR PDN-0191]`；legacy 2-dbu 步长在 HEAD 直接报错 | 全部量化为 5dbu 倍数（步长 10dbu） |
| 2 | 显式 `-spacing` 时 `pitch >= 2×(width+spacing)` | `[ERROR PDN-0175]`；如 met5 w=2.970/s=26.970 要求 pitch ≥ 59.880µm | `smax = p//2 − w`（legacy 用 `p−3w`，在 HEAD 过宽） |
| 3 | met4 width ≥ 1.18µm | via4 规则 M4M5_PR：cut 0.8 + 2×0.19 enclosure = 1.18µm；1.17µm 时**全部** M4–M5 via 失败（PDN-0110），随后 met5 stripe 被当 floating shape 删除（PDN-0200） | met4 最小 width 400 → 1180dbu |
| 4 | rail width ≥ 0.26µm | via1 规则 M1M2_PR：0.15 + 2×0.055 = 0.26µm；0.24/0.25µm 时 met1–met2 via **全部**失败，级联删除 met4+met5 stripe（PDN-0200） | railw 候选去掉 240dbu，用 [300,480,720,960] |

第 3/4 条的级联删除在 pilot 中造成整批 `unidentifiable` / `infer_fail`
（met5 整层消失；met4+met5 整层消失），已确认为 via 规则所致，
不是推断器 bug。主扫描限定在上述有效域内，这是**方法声明**，不是丢弃失败。

另有一条 HEAD 行为记录（不影响主扫描有效性）：
- 存在 rail↔strap connect 时，rail 会被延长到覆盖同 net 最远 strap 的 far edge
（如 VDD rail x2 从 269560 延到 269975 = 最后一根 VDD met4 stripe 的 far edge），
即使该 connect 的 via 全部失败（repair 行为）。在有效域内所有 connect 都有 via，
推断出的 connect 与真值一致，round-trip 能逐项复现该延长。

## 4. 主扫描方法

- 脚本：`phase7/randscan_head.py`（单 worker 串行，~4–8s/组）。
- 流程/组：采样 → `write_gen_tcl` 生成 → HEAD openroad 生成 ODB →
`extract_cpp.py` 抽取 → `pg_infer_cpp.py` 推断 → 9 参数逐项比较 →
推断配置重跑 pdngen → wire 矩形 + via 集合 multiset 全等（`collections.Counter`，
严格计 multiplicity）。
- 真值归档：`reports/rev6-head-truth/`（`MANIFEST.json` + `cfg_*.json`，200 组，
dbu 整数即真值，无需舍入）。
- connect 固定为 `{{met1 met4} {met4 met5}}`；starts_with 随机 POWER/GROUND；
仅 grid/stripes/rails（无 ring/macro）。

## 5. 主扫描结果（N=200，seed 20260930）

2026-09-28 一次跑完，单 worker 串行，共 22.6 分钟，**零生成失败**。

| 指标 | 结果 | 说明 |
|------|------|------|
| inference success | **200/200** | 推断器全部正常退出并给出参数 |
| measured round-trip pass | **200/200** | 推断配置重跑 HEAD pdngen，wire 矩形 + via 集合 multiset 逐项全等（实测，非等价论证） |
| exact parameter recovery | **200/200 = 100%** | width/pitch/offset/spacing（met4/met5）+ rail width + starts_with 逐项全等 |

状态分类：exact 200 / equiv 0 / unidentifiable 0 / fail 0 / error 0。
显式 spacing 覆盖约一半配置（采样 50%），dropout 分支（offset < width/2）在
`pg_infer_cpp.py` 内处理。N=200 未出现 AMBIGUOUS 对偶（rev5 Tcl 为 2/800），
样本量所限，不作对偶率结论。

## 6. 与 Tcl 版对照

| 实验 | inference | measured RT | exact |
|------|-----------|-------------|-------|
| rev5 fresh-seed sky130hd/gcd N=800（Tcl） | 800/800 | 800/800 | 798/800 = 99.75% |
| rev5 breadth N=800（Tcl，nangate45/asap7/aes） | — | — | 794/800 = 99.25%（3 fail 为 pdngen 浮点/dbu 裂缝） |
| rev3 原始 N=800（Tcl） | 734/800 | — | 732/800 = 91.5%（后被 dropout-aware 推断修正） |
| **rev6 HEAD N=200（本实验）** | **200/200** | **200/200** | **200/200 = 100%** |

## 7. E2 jitter 防御（HEAD 复现）

方法：照搬 `defense/run_e2.py`。met4 stripe 位置加抖动 δ∼Uniform(−j,+j)，
j ∈ {0, 2%, 5%, 10%, 15%} × pitch，非零档各 3 seeds；每根 stripe 连同其 via 栈
（含 met4–met5 via 的 x 坐标）一起平移。攻击者：naive `pg_infer_cpp`
+ robust 最小二乘 pitch 估计；防守方：连通性、dangling via、min spacing vs LEF、
comparative mesh（worst drop vs baseline）。

HEAD baseline：met1 w=0.480；met4 w/p/o=1.600/27.140/13.570µm；
met5 w/p/o=1.600/27.200/13.600µm；connect `{{met1 met4} {met4 met5}}`；
starts_with POWER。Baseline worst drop = 67.02 mV/A。

### 7.1 攻击者侧

| jitter | naive 退出码 | robust pitch 最大相对误差（nets×seeds 取最大） |
|--------|-------------|-----------------------------------------------|
| 0% | 0（正常） | 0.000% |
| 2% | 1（崩溃）×3 | 0.243% |
| 5% | 1（崩溃）×3 | 0.919% |
| 10% | 1（崩溃）×3 | 0.609% |
| 15% | 1（崩溃）×3 | 1.640% |

robust offset 绝对误差最大：2%→0.41µm，5%→0.82µm，10%→1.16µm，15%→2.90µm。

legacy 对照（`reports/phase-6-defense.md`，2026-09-26）：
naive 在 j≥2% 崩溃；robust 最大 pitch 误差 2%→0.21%、5%→0.76%、10%→0.97%、15%→1.19%。
HEAD 复现结论一致：naive 在 2% 即失效；robust 在 15% 抖动下仍把 pitch 恢复到 ~1.6% 以内。

### 7.2 防守方侧（13/13）

- 连通性：13/13 每 net 1 个连通分量（VDD/VSS 各一）。
- dangling via：13/13 均为 0。
- min met4 spacing：最小 4.159µm（15% 档），LEF 最小 0.3µm，全过。
- comparative mesh worst-drop 相对 baseline 变化：±0.91% 以内
（legacy 为 ±0.62%）。baseline 67.02 mV/A。

### 7.3 HEAD-only 的两个建模修正（已验证不改变 legacy 口径）

1. **via-stack 合并**：HEAD baseline 里所有 met5 stripe 的 y 恰好等于某 rail 的 y
（offset 取整所致），于是 met4–met5 via 与 rail via 栈在同一 (cx,cy) 合并成一条
(met1→met5) 链。`lib.build_mesh` / `lib.connectivity` 把整条链坍缩成单边，
导致中间层 met4 拿不到边：mesh 885 个注入节点不可达 ground、连通性数出 11 个分量。
物理上 via 栈连接穿过的所有层。`run_e2_head.py` 中的 `build_mesh_connected` /
`connectivity_connected` 把每条链展开成相邻**有线层**之间的边
（电阻 = 跨越的 via span 数 × R_VIA_OHM）。
等价性验证：legacy baseline 上与 `lib.build_mesh` 差值为 **0.0**
（legacy 无 met4–met5/rail 重合，展开前后边集相同）；`defense/lib.py` 未动，
legacy E2 数字不受影响。
2. 上述修正后 HEAD baseline mesh = 67.02 mV/A（legacy 同配置 66.90 mV/A，接近）。

## 8. 诚实边界

- 仅 sky130hd/gcd 这一个设计、一个 floorplan。
- N=200（Tcl 版为 N=800），固定两组 connect `{{met1 met4} {met4 met5}}`。
- 采样限定在 §3 的 HEAD 有效域内：5dbu 网格、pitch≥2(w+s)、met4 w≥1.18µm、
rail w≥0.26µm。域外的 via 规则级联删除行为已在 pilot 中刻画，不计入指标。
- 仅 grid/stripes/rails；不覆盖 ring、macro、blockage。
- E2 是 extracted-geometry 扰动（抽取后平移 stripe+via），不是 pdngen 参数本身
能表达的 jitter；mesh 是 comparative 指标，不是 signoff IR。
- E2 的 mesh/connectivity 用了 §7.3 的合并-stack 展开修正（legacy 口径下恒等）。

## 9. 文件清单

- `phase7/randscan_head.py` — 主扫描脚本（采样/生成/推断/round-trip）。
- `phase7/run_e2_head.py` — E2 复现脚本（含 `build_mesh_connected` /
`connectivity_connected`）。
- `phase7/e2_head_results.json` — E2 13 组完整结果。
- `reports/rev6-head-truth/MANIFEST.json` + `cfg_0000…cfg_0199.json` — 200 组真值。
- 本报告 `reports/rev6-expC-head-rescan.md`。

## 10. 工具链坑（给父代理的一句话之外）

1. HEAD C++ pdngen 对 5dbu 制造网格硬报错（PDN-0191）：legacy 的 2dbu/1dbu
步长采样器必须改成 5dbu 倍数，否则整批失败。
2. 显式 `-spacing` 时 pitch 必须 ≥ 2×(w+s)（PDN-0175），legacy 的 `p−3w` 上限在
HEAD 过宽，会整批触发硬错。
3. via 最小 enclosure 是硬门限：met4 w<1.18µm → 零 M4–M5 via → met5 整层被删
（PDN-0110→PDN-0200）；rail w<0.26µm → 零 M1–M2 via → met4+met5 整层被删。
这是 tech LEF 里 M4M5_PR（0.8+2×0.19）/ M1M2_PR（0.15+2×0.055）规则的直接后果，
不是推断器能"修"的——采样域必须避开。
4. legacy dict 传参 `pdngen $PDN_CFG` 在 HEAD 报 STA-0562，必须用
define_pdn_grid/add_pdn_stripe/add_pdn_connect 新 API。
5. `defense/lib.py` 的 mesh/connectivity 在 via-stack 合并时会把中间层断开
（HEAD 上 885 节点不可达、11 个假分量）；已在 `run_e2_head.py` 本地修正，
legacy 口径下数值恒等（diff 0.0），`lib.py` 本体未动。
