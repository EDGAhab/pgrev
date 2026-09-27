# rev3 WS1 — 无标签多边形攻击 MVP（sky130hd/gcd）

日期：2026-09-27 PDT · 工作目录 `~/pgrev` · 脚本 `/tmp/rev3/ws1/unlabeled.py`（scratch，未进 repo）

## 可行性结论（置顶）

**成。** 输入只有去标签多边形时，sky130hd/gcd 的全部 pdngen 几何参数被**逐项 exact 恢复**，
round-trip **PASS（含网名标签）**：133/133 wires、2907/2907 vias 逐矩形全等。

| 参数 | 真值 | 无标签反推 | 结果 |
|---|---|---|---|
| rails | met1 width 0.480 | met1 width 0.480 | exact |
| straps met4 | 1.600 / 27.140 / 13.570 | 1.600 / 27.140 / 13.570 | exact |
| straps met5 | 1.600 / 27.200 / 13.600 | 1.600 / 27.200 / 13.600 | exact |
| connect | {{met1 met4} {met4 met5}} | {{met1 met4} {met4 met5}} | exact |
| stripes_start_with | POWER | POWER | exact（含极性） |

反推配置与**带标签**管线输出逐字节一致（`diff` 无差异）；重建的
`pg_shapes.csv` 与原始带标签文件 3040/3040 行完全一致——标签恢复率 100%。

## 管线各步骤 verdict

1. **union-find 连通性** — work。同层 wire 相接/重叠、via 与上下金属 wire 重叠、
   相邻 cut 层 via 矩形 XY 重叠，三类边得到**恰好 2 个连通分量**（1597 / 1443 shapes），
   纯度 2/2（每个分量只含一个真值网）。运行 ~2 s。
2. **PG 网络识别** — 在本数据上退化为平凡成功（`pg_shapes.csv` 本来就只含 PG 形状，
   无信号网）。排序启发式（wire 数、bbox 面积）已实现；用**合成测试**补强：
   注入 300 条随机信号线（met2/met3 小矩形，互不相接）→ 302 个分量，
   top-2 仍是两个 PG 网（`synth_test.py`，PASS）。真实信号网混合仍是未验证项（见边界）。
3. **极性判定 VDD/VSS** — work，但**依赖 PDK 库知识**，见根本歧义 A1。
   rail 所在行边界 + row orient：N-orient 行上边 rail = VDD、下边 = VSS，FS 相反
   （tap cell 的 VPWR/VGND 上下位置是公开 PDK 信息）。96/96 rail 投票一致，
   两个分量极性 2/2 正确，`stripes_start_with=POWER` 正确恢复。
   该规则在另 3 个设计上用真值抽查：nangate45 58/58、aes 228/228、asap7 106/106。
4. **rail vs stripe 分类** — work。启发式：met1 + 水平 + width<1µm → RAIL（FOLLOWPIN），
   其余 STRIPE；96 rails + 37 stripes，相对真值 **0 误分类**。
5. **via 跨度还原** — work。主判据是 cut 层表（DEF VIARULES：cut 层物理上只存在于两层
   特定金属之间，属工艺栈知识）；overlap 验证：via1 全部 912 个压住 met1 rail，
   via4 全部 171 个同时压住 met4+met5 stripe，via3 全部 912 个压住 met4 stripe；
   via2/via3（met2-met3 / met3-met4）不压任何 wire——此间无 met2/met3 wire，
   跨度完全由 cut 层表 + 与上下 via 的堆叠对齐给出（脆弱点，见 A5）。
6. **pg_infer 复用** — work，无需改 `pg_infer.py` 一行。重建带标签 csv →
   新建 `data/sky130hd_gcd_unlabeled/`（拷入 design_meta.json、floorplan.def、
   pdn_truth.cfg）→ `python3 src/pg_infer.py --tag sky130hd_gcd_unlabeled` 直接跑通。

## 根本歧义清单

- **A1（Z2 命名对称性——已用库知识消解，本 MVP 的核心发现）：**
  纯几何上，VDD/VSS 全局互换 + `stripes_start_with` 翻转**不可区分**
  （两套 stripe 网格几何全等、rail 交替、via 栈保持网内连接）。
  这是*命名*对称性而非几何对称性：一旦任一网被锚定，对称性即破缺。
  本 MVP 用 row orient + tap-cell 规则锚定了 rails（96/96），从而消解。
  **没有 PDK 库知识的攻击者只能恢复到 Z2 等价类**——论文里必须正面写这一句。
- **A2：** 网名字符串（"VDD"/"VSS"）本身是标签。本 MVP 的网名取自 DEF
  SPECIALNETS 的 USE POWER/GROUND（标签泄漏，见边界 B3）；几何只给出"网 A / 网 B"。
- **A3：** 死参数（`halo`、`rails_start_with`、rail pitch/offset）无几何效应——
  phase 5 已证伪其可辨识性，无标签情形下结论不变。
- **A4：** macro grid、pin 名、blockage、global connections 本来就不在几何中（phase 4 已有）。
- **A5（脆弱点，非歧义）：** 中间层 via（via2/via3）不接触任何 wire，跨度识别
  100% 依赖 cut 层分组正确 + 堆叠 XY 对齐。若成像把 cut 归错一层，
  跨度链整体错位——这是从"去标签 ODB"到"真实成像"之间最脆的一环。

## 诚实边界（本 MVP 不是什么）

- **B1：** 输入是"去标签的 ODB"，不是真实成像多边形。保留的假设：
  每层多边形归属已知（按层成像是标准假设）、via-cut 矩形按 cut 层分组、
  金属叠层顺序已知、DIEAREA/ROW 几何可观测。真实 delayering 的对准误差、
  漏检/误检、cut 层归属噪声**一概未建模**——仍是 future work，论文中不得声称已覆盖。
- **B2：** `pg_shapes.csv` 本来只含 PG 形状；信号网分离只在合成测试中验证（300 线 PASS），
  真实混合版图未测。
- **B3：** `floorplan.def` 按任务要求原样拷入，其 SPECIALNETS 含 VDD/VSS 网名与
  USE 标注——这是标签泄漏。`pg_infer.py` 用它写 `power_nets`/`ground_nets` 与
  `stripes_start_with` 的字符串取值；**几何恢复不依赖它**（只影响命名）。
  完全诚实的下一版应匿名化 DEF 网名后再跑。
- **B4：** 极性规则（N-top=VDD）是 PDK 库知识（tap cell 版图公开信息），非纯几何可观测量。
  规则本身在 4 个设计上用真值验证过（96+58+228+106 / 全对），但它属于"攻击者已知 PDK、
  未知设计"的标准威胁模型假设，需在论文中显式声明。
- **B5：** VIARULES（cut 层连哪两层金属）视为已知工艺栈信息；cut 层表错则跨度全错（A5）。

## Round-trip

用反推配置重跑 ORFS PDN 步骤（`src/roundtrip.sh sky130hd_gcd_unlabeled
designs/sky130hd/gcd/config.mk sky130hd gcd`，legacy 工具链，`source env.sh`），
抽取几何后 `src/pd_diff.py` 对比：**wires 133/133、vias 2907/2907，ROUNDTRIP PASS**
（含 net 标签键——极性恢复正确，否则此处必 FAIL）。

环境备注：本机 `/usr/bin/time` 缺失（VM 更换后 /usr 未持久化），临时用
`exec "$@"` 垫片补上，仅影响计时显示，不影响结果。后续 round-trip 若在新 VM 上跑，
需重装 `time` 或保留垫片。

## 推广到其余 3 个设计的工作量评估（未实跑）

管线中写死的两处需参数化：`order` 金属栈（应从各设计 DEF 的 VIARULES 解析，
现为硬编码 met1..met5）、rail 启发式的 `layer=="met1"`（应改为"最底层若干薄水平线层"）。

| 设计 | 差异点 | 预估工作量 |
|---|---|---|
| nangate45/gcd | rail 仅 metal1；strap metal4/metal7；via 链 metal1→metal7。结构同源，极性规则已验证 58/58 | 小（参数化层名即可） |
| sky130hd/aes | 结构与 gcd 相同，量级大（16403 vias，228 rails） | 小+**性能**：现有 via-via 双重循环 O(V²) 在 aes 上约 2.7 亿次重叠检查，Python 不可行，需加空间索引（grid bucket）。算法不变 |
| asap7/gcd | **两层 rail（M1+M2）**：rail 启发式需支持多 rail 层；strap M5/M6 带 spacing（pg_infer 已处理）；极性规则已验证 106/106 | 中（rail 层推断逻辑要重写：按"薄水平线层"聚类而非指定层名） |

共性：4 个设计的 `pg_shapes.csv` 都只含 PG 形状，信号网分离的真实验证在所有设计上都缺；
asap7 的 M1/M2 双 rail 层是唯一需要改启发式的结构性差异。

## 文件

- 报告：`~/pgrev/reports/rev3-ws1-unlabeled.md`（本文件）
- 数据：`~/pgrev/data/sky130hd_gcd_unlabeled/`（`pg_shapes.csv` 重建带标签版、
  `design_meta.json`、`floorplan.def`、`pdn_truth.cfg` 拷入、`pdn_inferred.cfg` 为本次反推输出）
- Scratch（未进 repo）：`/tmp/rev3/ws1/unlabeled.py`（主流程）、`/tmp/rev3/ws1/synth_test.py`（合成信号网测试）
