# Phase 1 汇报：安装 OpenROAD-flow-scripts

结论：**通过**（路线有偏离，见下）

## 做了什么
1. **路线 A（预编译 .deb）失败**：Ubuntu 22.04 的 .deb 在本机 Ubuntu 24.04 上无法安装——`libpython3.10` 不可装，且 Qt5 已从 24.04 官方仓库移除（`libqt5core5a` 等无候选）。转用手册备选方案：conda 安装（事先核实 litex-hub 频道有 linux-64 构建）。
2. **OpenROAD 定格在 2022-03 构建**（`2.0_3175_gf12e2f474`）：litex-hub 上更新的构建依赖 `libboost 1.73` 等已下架的包，solver 无解。为版本配平，ORFS checkout 到 2022-04-14 的 commit（`96eb3de`，tarball 方式获取，全量 git clone 太慢）。
3. **Yosys** 按手册用 oss-cad-suite（2026-09-26 当日构建），版本 0.69，满足手册 ≥0.58 要求。
4. 修了两个环境坑：
   - Makefile 里 `SHELL ?= /bin/bash` 因环境变量 SHELL 已存在而不生效 → 调用时显式 `make SHELL=/bin/bash`；
   - 本机无 `/usr/bin/time` 且 apt 装不上 → 放了个 `exec "$@"` 垫片（峰值内存改用自研 Python 采样器记录）。
5. 默认 `make` 跑完 **nangate45/gcd 全流程**：synth → floorplan → place → CTS → route，一直到 `6_final.def` / `6_final.odb` / `6_final.v` / `6_final.spef`。最后一步 KLayout GDS 合并因无 KLayout 而停，按手册"可以跳过"处理。

## 关键数据
- 总用时：约 3 分钟（分 3 次增量调用；gcd 是极小设计）
- 峰值内存：约 660 MB（进程树 RSS 采样）
- 磁盘占用：`tools/` 5.1 GB（含 conda 环境、oss-cad-suite、ORFS）
- `openroad -version` → `f12e2f474`；`yosys -V` → `0.69+154`

## 遇到的问题及处理方式
见上。核心教训：24.04 上不要赌 22.04 的 .deb；conda 的旧构建+solver 行为需要人工干预选版本。

## 下一步建议
进入 Phase 2：跑 sky130hd/gcd 到 floorplan，找 PDN 真值脚本并导出 DEF。注意 sky130 PDK 可能需要下载，先看 flow 是否自动处理。
