# rev5 实验 A：随机扫描真值重跑（N=800，seed 20260929）

日期 2026-09-27 PDT。目标：回应审稿人对 rev4 dropout 修正的循环性质疑
（"dropout 规则是用失败例调出来的"）——用**全新种子**重跑 N=800，
**真值 JSON 全部进 repo**，逐项对照真值统计三指标。
推断器为冻结的 rev4 dropout-aware 版本（`src/pg_infer.py`，commit 前回归
`--tag sky130hd_gcd` 输出 byte-identical）。

## 1. 为什么不用原种子 20260927

尝试复现原 800 配置，结果**不可复现**，实证如下：

- 用 seed 20260927 + repo 内 `src/randscan.py` 采样器重采样 cfg0，
  得 `railw=240`，而保留的原扫描几何 `data/ws2_0000/pg_shapes.csv`
  的 rail 宽为 480 dbu；
- 原扫描真值含奇数 dbu 参数（如 ws2_0000 推断 `pitch 39.767`/`offset 19.689`），
  而现采样器 `randrange(..., 2)` 只产偶数；
- 对 6 种抽取顺序 × step{1,2} 穷举，前 3 组真值（以保留推断 cfg 为代理）
  最好只命中 5/30 ≈ 随机水平。

结论：原扫描用的是已清理的 /tmp scratch 采样器，抢救进 repo 的版本
采样分布相同但抽取序列不同。**改用新种子 20260929**（`random.Random`，
全 primary 800 组）。这反而是更强的验证：dropout 修正规则是在原 66 个
失败例上调出来的，在 800 组**全新样本**上做样本外（out-of-sample）验证，
直接回应循环性质疑。

## 2. 方法

管线（与 rev3/rev4 同构）：真值 cfg → `pdngen $PDN_CFG`（`/tmp/rs/run_pdn.tcl`，
按 ORFS `pdn.tcl` 语义重建：`read_db` → `pdngen $PDN_CFG -verbose` →
`write_db`；原文件随 tmpfs 丢失）→ export DEF + dump wire/via →
`pg_extract.py` → `pg_infer.py`（dropout-aware，冻结）→ 与真值逐项对照 →
**所有可推断组实测 round-trip**（rev5 新增：exact 组不再依赖确定性论证，
直接重跑 pdngen 比对 wire/via 全集）→ dual-config 对偶检验。

相对 rev4 驱动的三处改动（`src/randscan.py`，本次 commit）：

1. `main()` 采样后立即写 `reports/rev5-scan-truth/cfg_%04d.json`
  （`sampled` + `truth_dbu` 双份）+ `MANIFEST.json`
   （seed=20260929，n_primary=800，采样器标识，git commit）；
2. `worker()` 记录真值几何 `pg_shapes.csv` 的 md5（`shapes_md5`），
   供未来交叉核验；
3. round-trip 改为**无条件实测**（exact 组也重跑），状态机新增
   `fail_exact_rt`（本次 0 触发）。

判据（论文计数口径，worker 的 `compare()` 比任务书更严，
用整数 dbu 全等而非 ≤2dbu——满足 dbu 全等必满足 ≤2dbu）：

- **inference success**：推断器产出配置（status ∈ {exact, equiv, unidentifiable}；
  本次无 infer_fail/error）；
- **round-trip pass**：重跑 pdngen 后 `pd_diff.py` 判定 wire/via 全集一致；
- **exact**：参数逐项 dbu 全等 **且** `starts_with` 一致 **且** round-trip 通过。

运行：2 worker（VM 仅 2 核，保守并行），wall 约 32 分钟，
平均 4.8 s/组，总计 1.07 core-h。800/800 结果文件齐，无缺失；
真值审计（worker 记录 truth vs 归档 `cfg_*.json`）：**0 不一致**。

## 3. 三指标结果（N=800）

| 指标 | 结果 |
|---|---|
| inference success（产出配置） | **800/800 = 100%** |
| round-trip pass（几何 wire/via 全同，全部实测） | **800/800 = 100%** |
| exact（参数 dbu 逐项全等 + starts_with 一致） | **798/800 = 99.75%** |
| 几何等价 equiv（参数不可辨，几何全同） | 2/800（§4 逐项） |
| unidentifiable（单 stripe 根本不可辨） | 0/800 |
| 失败（infer_fail / error / rt 不通过） | **0** |

等价类单列：`AMBIGUOUS`（多全局一致假设并列）1 组（cfg 0462）；
Class P / Class S 碰撞 0 组；dual-config 对偶检验 `dual_equiv=True` 0/800
（与 rev3 一致：3 位小数截断使对偶 offset 差 ≤1 dbu，无 MD5 全等）。

dropout 修正分支：**60/800（7.5%）组触发**（触发原因 60×
`inconsistent starts_with across layers`，0× bad spacing），
其中 59 组恢复为 exact，1 组（0462）为 AMBIGUOUS equiv。
触发率与原扫描的 66/800（8.25%）分布一致。

## 4. 与 rev4 数字对比

| | rev4（原 800 几何重推断，真值已失） | rev5（新 800 样本，真值归档） |
|---|---|---|
| inference 成功 | 800/800 (100%) | **800/800 (100%)** |
| 几何 round-trip 通过 | 800/800 | **800/800（全部实测，含 exact 组）** |
| 参数严格恢复 exact | 796/800 (99.5%) | **798/800 (99.75%)** |
| equiv | 4/800（2 原有 + 0082/0507） | 2/800（0462 AMBIGUOUS + 0578 广义对偶） |
| 失败 | 0 | **0** |
| 真值对照方式 | 64 组靠"唯一性+round-trip"论证 | **800 组逐项对照归档真值** |

## 5. 非 exact 案例逐项归因（共 2 组，无失败）

**cfg 0462** — `equiv`，AMBIGUOUS。真值
`(GROUND, railw 240, met4 {w1724 p8240 o4966}, met5 {w2168 p39882 o540})`；
推断输出 `(POWER, met4 {o846}, met5 {o20481})`，width/pitch 全对。
两组参数生成逐 dbu 相同的几何（dropout 引入的命名对称性：
met4 base VDD k=1 vs base VSS k=0 的对偶），输出已标
`AMBIGUOUS: 2 globally-consistent hypotheses` NOTE。这是 genuine 几何
不可辨（参数层），非推断器缺陷；round-trip bit-exact
（wires 170/170，vias 9300/9300）。

**cfg 0578** — `equiv`，广义对偶重参数化（非 dropout 路径，naive 直接产出）。
真值 `(GROUND, met4 {o418 s2122}, met5 {o362 s10086})`；
推断 `(POWER, met4 {o4920 s16348}, met5 {o12052 s8910})`，
即 `starts_with` 翻转 + offset/shift 重参数化（VSS shift 取
`spacing+width` 而非 `pitch/2`）。width/pitch 全对，几何全同，
round-trip bit-exact（wires 141/141，vias 3421/3421）。
同 rev3 原扫描 0346 / 复现扫描 0672、0676 现象。

示例 dropout 恢复（cfg 0012，exact）：真值
`(GROUND, railw 480, met4 {w2752 p18534 o630 s6218}, met5 {w2044 p18794 o17964})`
与推断输出**逐项一致**；NOTE 记录
`met4: base net VSS, 1 leading stripe(s) dropped` /
`met5: base net VSS, 0 dropped`，前向模型验证通过。
59 个同类案例全部如此——修正分支在新样本上逐项精确恢复，
非记忆原 66 例。

## 6. 真值文件位置说明

- 目录：`reports/rev5-scan-truth/`（801 个文件，内容 273 KB；
  du 显示 3.2M 系 4K block 对齐所致）。
- `cfg_%04d.json`：`{"i", "kind", "sampled"（采样原始值）,
  "truth_dbu"（取整后真值，即对照基准）}`。
- `MANIFEST.json`：seed、各类数量、采样器标识、采样时 git commit、
  800 个文件名清单。
- 结果明细（800 个 worker JSON，含 inferred/diffs/rt_detail/shapes_md5）
  在 `/tmp/rs/results/`（tmpfs，未进 repo；三指标已固化于本报告 §3）。
- 扫描日志：`logs/rev5-scan.log`。

审稿人可复现：`source env.sh && python3 src/randscan.py 20260929 800 0 0`
（需 legacy 工具链；2 核 VM 约 35 分钟）。注意 `random.Random(20260929)`
跨 Python 3.x 版本确定性成立，采样器即本次 commit 的 `src/randscan.py`。

## 7. 局限

1. 本次 800 组全为 primary 采样（沿用原扫描口径），未含
   directed_spacing / high_pitch 定向探针；高 pitch 退化边界仍以 rev3
   seed-7 扫描（N=630）为准。
2. `exact` 判据为 dbu 整数全等（严于任务书的 ≤2dbu），数字是下界口径；
   若按 ≤2dbu 计，0578 类广义对偶仍不算 exact（offset 差远超 2dbu），
   结论不变。
3. AMBIGUOUS 的 tie-break（POWER 优先）是确定性的，选择本身无信息量，
   与 rev4 报告 §9.3 一致。
