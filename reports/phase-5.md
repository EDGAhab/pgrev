# Phase 5 — 往返验证（round-trip）与变体实验

日期：2026-09-26 PDT · 脚本：`src/roundtrip.sh`、`src/pd_diff.py`

## 往返方法

用**反推配置** `pdn_inferred.cfg` 重跑 ORFS 的 PDN 步骤，再抽取几何并对比。
为不污染原始结果：新建 `/tmp/rt/<tag>/`，软链接 `2_5_floorplan_tapcell.odb`
和 `1_synth.sdc`，`make` 时覆盖 `RESULTS_DIR`、`LOG_DIR`、`PDN_CFG`
（`PDN_TCL` 本就未设置，走 `pdngen $PDN_CFG` 分支）。判据：wire 矩形
（1 dbu 容差内）与 via 集合**完全一致**。

## 往返结果：4/4 PASS

| 设计 | wires（原/重跑） | vias（原/重跑） | 结论 |
|---|---|---|---|
| sky130hd/gcd | 133 / 133 | 2907 / 2907 | PASS，逐矩形全等 |
| nangate45/gcd | 65 / 65 | 279 / 279 | PASS |
| sky130hd/aes | 318 / 318 | 16403 / 16403 | PASS |
| asap7/gcd | 114 / 114 | 432 / 432 | PASS |

反推配置省略了 `halo`、`rails_start_with`、rail pitch/offset 后仍逐矩形全等，
**实证**了这些参数的几何无关性（不只是源码阅读的结论）。

## 变体实验（sky130hd/gcd）

| 变体 | 改动 | 几何 | 再反推 |
|---|---|---|---|
| v_pitch | met4 pitch 27.14→30.00 | 变化（met4 相关 via 从 171→153 等，共 2601 vias） | 正确恢复 pitch=30.000 |
| v_start | stripes_start_with POWER→GROUND | 变化（VDD/VSS 网格互换） | 正确恢复 starts_with=GROUND |
| v_dead | +rails_start_with=GROUND, halo=5, rail pitch 9.99/offset 3.33 | **全等**（133w/2907v） | ——（死参数实证） |
| v_conn | connect {{met1 met4} {met4 met5}} → {{met1 met5}} | **0 vias**（全部被跳过，PDN-0042 警告） | —— |

### 结论

1. 反推对真实参数变化敏感：pitch、starts_with 的改动都被几何捕捉且可再恢复。
2. 死参数确认：`rails_start_with`、`halo`、rail pitch/offset 可任意改而不影响几何。
3. **connect 粒度可辨识**：拆分对产生完整 via 栈（2907），单条高跨对
   `{{met1 met5}}` 产生 **0** 个 via——pdngen 的 via 逻辑要求 connect 对位于
   相邻 grid 层之间。Phase 4 中“高跨等价”假设被此实验**证伪**，如实记录。

## 手册判据对照

- Phase 5 主判据（几何 exact match）：4 个设计全部达到。
- 参数文本非完全一致是**预期内**的：差异仅限于已证明无几何效应的死参数。
- 非单射性的实证边界：死参数构成平凡等价类；connect 粒度、pitch、offset、
  spacing、starts_with 均可辨识，未发现非平凡等价类。
