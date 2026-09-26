# Phase 2 报告：真值 PDN 脚本 + floorplan DEF（4 设计）

日期：2026-09-26 PDT
前置：Phase 1（openroad 2022-03 构建 f12e2f47 + yosys 0.69 + ORFS 2022-04-14）

## 重要偏离（相对执行手册）

手册假设真值脚本为 `platforms/<plat>/pdn.tcl`（`define_pdn_grid` 新语法）。
实际 ORFS 2022-04-14 中：
- sky130hd/nangate45：`platforms/<plat>/pdn.cfg`
- asap7：`platforms/asap7/openRoad/pdn/grid_strategy-M2-M5-M7.cfg`（`PDN_CFG` 默认值）
- 语法是旧版 `pdngen::specify_grid`（`pdngen::specify_grid stdcell { rails {...} straps {...} connect {...} }`），
  不是 `define_pdn_grid/add_pdn_stripe`。反推目标相应调整为该语法（见 Phase 4）。

`define_pdn_grid` 等新 API 在该版本 PdnGen.tcl 中虽已存在，但 ORFS 2022 流程实际走 `pdn.cfg` 路线。

## 产物（data/<tag>/）

| 设计 | 真值 cfg | floorplan.def | DEF sanity（STRIPE/FOLLOWPIN 行数） |
|---|---|---|---|
| sky130hd/gcd | pdn_truth.cfg (1512 B) | 318 KB | 2944 / 96 |
| nangate45/gcd | pdn_truth.cfg (556 B) | 83 KB | 286 / 58 |
| sky130hd/aes | pdn_truth.cfg (1512 B) | 2.9 MB | 16493 / 228 |
| asap7/gcd | pdn_truth.cfg (1407 B) | 92 KB | 440 / 106 |

DEF 均含 `SPECIALNETS` 段；STRIPE 与 FOLLOWPIN 形状齐全。

## 耗时/内存（run_with_mem.py 采样进程树 RSS）

- sky130hd/gcd floorplan：wall 7.2 s，peak RSS 78 MB（2026-09-26 00:25 PDT）
- 其余三设计顺序执行，总 wall 约 60 s 内完成（见 logs/phase2_more.log）

## Pass 判定

✅ 通过。4 个设计的 `pdn_truth.cfg` 与 `floorplan.def` 齐全，
DEF 中 STRIPE/FOLLOWPIN 形状数量级合理（与后续 Phase 3 抽取的 wire/via 计数一致）。
