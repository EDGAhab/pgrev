# Defense 设计：抗反推 PDN（anti-reverse-engineering PDN）

日期：2026-09-26 PDT · 性质：设计/范围文档（未跑重实验，只做了只读工具核查）
前置：`reports/phase-4.md`（攻击：反推器）、`reports/phase-5.md`（往返验证）

## 0. 威胁模型与攻击者画像（精确版）

- **攻击者能力**：拿到完整版图几何（GDSII/DEF/ODB 级别，即制造后反向工程）。
  能区分 POWER/GROUND net（SPECIALNETS 的 USE 标记），能看到所有 wire 矩形和 via。
- **攻击者目标**：恢复 `pdngen::specify_grid` 的几何相关参数
  （每层 width/pitch/offset/spacing、connect 对、starts_with）。
- **我们的反推器依赖的 5 个假设**（defense 就打这些）：
  - A1：每层每网的 strap 中心构成**等差数列**（单一 pitch），容差 ±2 dbu 即断言失败；
  - A2：VSS 网格 = VDD 网格 + **固定 shift**（pitch/2 或 spacing+width）；
  - A3：via 的 (bottom, top) 跨度能组成**干净链条**，collapse 即得 connect 对；
  - A4：rail 宽度每层唯一、位置由 row 边界决定；
  - A5：offset 的参考系是 `(stdcell_xMin, stdcell_yMin − max_rail_width/2)`。
- **防御目标**（缺一不可）：(i) 让反推**失败或输出错误参数**（可测量）；
  (ii) PDN 仍是**合格**的供电网络（可验证的标准要诚实定义，见 §2）。

相关工作（已核实真实存在）：split manufacturing 攻防综述
[arXiv:2006.04627](https://arxiv.org/abs/2006.04627)；门级 camouflaging
[PLOS ONE 10.1371/journal.pone.0257679](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0257679)；
logic obfuscation 综述 [TODAES 2019](https://www.jinyier.me/papers/TODAES19.pdf)。
**未发现针对 PDN 参数反推的 obfuscation 文献**——这是 novelty 所在，但也要诚实：
PDN 与逻辑 camouflage 不同，它受欧姆定律约束，能"藏"的自由度小得多。

---

## 1. 候选混淆机制（逐个打反推器的假设）

### D1：悬空 decoy stripe（无 via 的假 stripe）

- **做法**：在 strap 层插入与真 stripe 同宽但**不打 via、不连任何 net**
  （或连到 net 但悬空）的 decoy stripe，位置选在真网格的间隙
  （如真 pitch P 的 P/4、3P/4 处）。
- **打哪个假设**：A1。反推器按 (net, layer) 分组后算中心差，
  decoy 若被划入某 net（悬空则无 net 归属——注意：悬空 stripe 在 DEF 里
  不属于 POWER/GROUND net，我们的抽取脚本只看 special net，
  **悬空 decoy 根本进不了反推输入**，这是个关键细节）。
  - 若 decoy 悬空：对**我们的**反推器**零效果**（直接被过滤）。
    要想有效果，decoy 必须挂在 VDD/VSS net 上（D3）。
  - 若 decoy 挂网但无 via：A3 的 via 链不受影响，但 A1 的等差数列被破坏
    （`assert max(abs(x-p)) <= TOL_DBU` 直接抛异常 → 反推崩溃，可测量）。
- **物理约束**：悬空金属本身 DRC 没问题（满足 spacing 即可），但它**占用布线资源**、
  增加耦合电容；挂网无 via 的 decoy 对 IR 无帮助纯属累赘。
- **会被更聪明的攻击者 trivially 击败**：按"有无 via"过滤 stripe
  （一行代码），decoy 全部现形。**结论：D1 单独是弱防御**，只能作为 D3 的对照组。

### D2：pitch 抖动（jittered stripe 位置）

- **做法**：每个 strap 中心加独立扰动 `δ ~ Uniform(−j, +j)`，
  j 取 pitch 的 5%–15%。用 ODB Tcl 后处理：平移 stripe 矩形及其附带的
  via 栈（via 与 stripe 一起平移，保持对齐）。
- **打哪个假设**：A1（等差数列不再精确成立）。反推器的 pitch 检测是
  `Counter(round(diff))` 取众数 + 全序列容差断言；jitter 超过 ±2 dbu
  即触发断言失败。sky130hd met4 pitch=27140 dbu，±5% = ±1357 dbu，
  远超容差——**必崩**。
- **物理约束**：
  - DRC：扰动后相邻 stripe 间距仍需 ≥ min spacing（LEF 可查），j 上限受此约束；
    stripe 与 perpendicular 走线的 via 包络也要 DRC-clean。
  - IR：平均金属密度不变，一阶 IR 近似不变（需 §2 的电阻 mesh 验证）。
  - Routability：stripe 位置抖动 → 固定 pitch 假设的布线器可能多花代价，
    但 PDN 在 floorplan 阶段已定，detail route 只需避让。
- **会被更聪明的攻击者部分击败**：攻击者把 TOL 放宽、用 RANSAC/最小二乘
  拟合 pitch，仍能恢复**近似** pitch（误差 ~j）。防御效果是"降精度"而非"致盲"。
  可测量：恢复 pitch 误差随 j 单调增——这本身就是个漂亮的实验曲线。

### D3：带 via 的交织 decoy 网格（interleaved decoy grid）★主推

- **做法**：在 strap 层插入**第二套完整网格**：同层、同宽、挂在**相同**
  VDD/VSS net 上、**打满 via 栈**，位置取真网格的 `+P/4`（或 `+P/2` 形成
  双倍密度假象）。Decoy 与真 stripe 在物理上无区别——都是真供电网络的一部分。
- **打哪个假设**：A1 + A2。反推器看到每网每层 2N 条 stripe，
  中心序列变成两个交织的等差数列：
  - 若 decoy offset = P/4：众数 pitch 检测可能给出 P/2（错误），
    或断言直接失败（取决于实现）；
  - VSS 相对 VDD 的 shift 假设（A2）也被污染，因为"哪个是 base 网格"
    变成 4 选 2 的组合问题。
  - 更重要的是：**via 连通性过滤器对 D3 无效**（decoy 全是真 via、真连通），
    这是 D3 与 D1 的本质区别。
- **物理约束**：
  - 这是**加金属**，IR 只会变好（并联电阻），EM 只会变好——
    defender 侧的物理判据反而容易过，这是 D3 的最大优点；
  - 代价：布线阻塞（多一倍 stripe）、via 数量翻倍、可能影响 routability；
    DRC spacing 必须满足（P/4 交织要求 P ≥ 4×(width+spacing)，对 sky130hd
    met4：P=27.14µm，width+spacing 远小于此，成立；asap7 M5：P=11.88µm，
    width 0.12+spacing 0.072=0.192µm，P/4=2.97µm ≫ 0.192µm，成立）。
- **攻击者升级**：可尝试"子集枚举"（2N 选 N 找等差子集）——组合爆炸但 N 小时
  （如每网 9 条 → C(18,9)=48620）暴力可解。**诚实记录**：D3 防的是"朴素反推器"，
  防不住"知道有 decoy 的自适应攻击者"做子集搜索；但子集搜索本身需要先验
  （decoy 比例、offset 模式），且恢复出的"真值"仍有 N 选 1 的歧义
  （真网 vs decoy 网不可区分——这正是我们想要的**不可辨识性**！）。
  这是全文档最接近"非平凡等价类"的东西：真 stripe 与 decoy stripe
  **物理不可区分**，攻击者即使完美提取几何，也无法判定哪套是"原始设计意图"。

### D4：via 稀疏化/非对称 via（打 connect 反推）

- **做法**：随机删除 X% 的 rail→strap via 栈（保留 strap→strap），
  或整层删掉某个 span（如删掉全部 met2-met3 via）。
- **打哪个假设**：A3。链条断裂 → connect 对被误判（如推断出
  `{met1 met3}` 式跳跃对，或链碎成多段）。
- **物理约束**：via 是电流瓶颈；删 via 直接恶化 IR/EM。
  必须保留足够冗余（defender 判据：电阻 mesh 最坏压降退化 ≤ 阈值，如 10%）。
- **弱点**：攻击者**不需要 via** 也能恢复 width/pitch/offset/spacing/starts_with
  （全从 wire 几何来）；D4 只污染 connect。这是**最弱**的独立防御，
  只适合做"connect 可辨识性"的对照实验（呼应 phase-5 的 v_conn 证伪）。

### D5/D6（次要，不主推）

- D5 非标准 rail（如隔行跳过）：只动 A4，但 rail 本来就不是"秘密"
  （位置由 row 决定是公开知识），防御价值低。
- D6 stripe 宽度调制（如宽窄交替）：动 A4 的 width 众数检测；
  50/50 宽窄比时"哪个是真 width"有歧义。但 width 本来就是最容易
  从单条 stripe 恢复的参数，调制只增加 DRC 复杂度，收益小。

**小结表**：

| 机制 | 打的假设 | 朴素反推效果 | 物理代价 | 聪明攻击者能否破 |
|---|---|---|---|---|
| D1 悬空 decoy | A1（部分） | 被 net 过滤，**无效** | 布线资源 | 一行过滤即破 |
| D2 pitch 抖动 | A1 | 断言崩溃 / 降精度 | DRC spacing 上限 | RANSAC 恢复近似值 |
| D3 交织 decoy 网格 | A1+A2 | pitch 误判或崩溃；真/decoy 不可区分 | 布线阻塞（IR 反而变好） | 子集搜索可破，但"意图"仍不可辨 |
| D4 via 稀疏化 | A3 | connect 误判 | IR/EM 直接退化 | wire-only 反推不受影响 |

---

## 2. 工具可行性核查（已实测，不臆测）

### 2.1 OpenROAD 自带 `analyze_power_grid`：存在但不可用做 signoff

实测（`~/pgrev/tools/eda/bin/openroad`，commit f12e2f47）：

- 命令**存在**：`analyze_power_grid`、`set_pdnsim_net_voltage`、
  `check_power_grid`、`report_power` 均为已注册命令（PSM 模块）。
- 在 `results/nangate45/gcd/base/6_final.odb` 上**能跑通**：
  建出 1097 个 PDN 节点，默认 checkerboard bump 模型，
  报出 `PSM-0040 All PDN stripes on net VDD are connected`。
- **但是**：无电流源时 worst-case IR drop = **4.33e-14 V（恒为零）**；
  加了 `set_power_activity -input -activity 0.2` 后**依然是零**——
  该版本 PSM 不从 OpenSTA 功耗分析取实例电流，且**没有任何命令**
  可以注入逐实例电流源（已枚举全部 `*current*`/`*bump*`/`*vsrc*` 命令，
  只有 `set_bump`/`set_bump_options` 管 bump 位置）。
- ORFS 2022 的 `final_report.tcl` 确实调了它，但 gate 在
  `RCX_RULES` + `PWR_NETS_VOLTAGES`/`GND_NETS_VOLTAGES` 之后，
  且电流源问题依旧——即使把 flow 跑通，结果也是 vacuous 的零。

**结论：本环境没有可信的开源 IR-drop signoff 工具。**论文里必须诚实写。

### 2.2 诚实的替代方案（defender 侧物理判据）

按可信度排序：

1. **连通性 + DRC（硬门槛）**：`check_power_grid` 的 PSM-0040
   （全网连通）实测可用；DRC 用 flow 自带 drc 步骤。
   这是" PDN 没断"的底线证明。
2. **一阶电阻 mesh 对比（comparative，非 signoff）**：从
   `pg_shapes.csv` 的 wire 矩形 + via 位置自建集总电阻网络——
   sheet 电阻从 tech LEF 的 `RESISTANCE RPERSQ` 直接读
   （已核实 sky130hd：met1 0.125、met4 0.047、met5 0.0285 Ω/□，
   各布线层齐全），电流注入用**均匀电流密度假设**
   （总电流按标准单元面积均摊到 rail 节点），scipy 稀疏求解
   （已核实 scipy 1.11.4 可用）。比较 baseline vs obfuscated 的
   worst-case/average 压降**相对变化**。
   必须明确标注的假设：均匀电流（无真实功耗向量）、标称 via 电阻、
   无封装/板级模型、静态直流。这是"探索期 PDN 对比"的常规做法，
   诚实标注即不算 oversell。
3. **EM**：无开源工具；用电阻 mesh 的支路电流估算电流密度，
   与 LEF/工艺手册的 EM 限值做数量级对比（只能算 sanity check）。

### 2.3 一个额外可用的实证

Phase-5 的 v_conn 已证明：`connect {{met1 met5}}` 高跨对产生 **0 via**
（PDN-0042 全部跳过）。这说明 pdngen 的 via 逻辑本身对"非常规"
connect 组合是脆弱的——defense 实验里任何改动 connect 语义的尝试
都要先过这一关（否则几何直接塌了，连"合格 PDN"都不是）。

---

## 3. 具体实验设计（3 个，按推荐顺序）

### 实验 E1：交织 decoy 网格（D3）——主推

- **对象**：sky130hd/gcd（最快，PDN 步 ~6 s），成功后复刻到 nangate45/gcd。
- **精确操作**：
  1. 从 `data/sky130hd_gcd/2_6` 级 ODB（或重跑 roundtrip）出发，
     写 ODB Tcl 脚本：对 met4 每条真 stripe，在 `x_center + pitch/4`
     处复制一条同宽 stripe（net 归属与真 stripe 相同），
     并把该 stripe 的全部 via 栈平移复制（`dbBox` 级复制，
     保持 via 与 stripe 的相对位置）；
  2. met5 同理（pitch/4 交织）；
  3. DRC 检查（flow drc 或至少 stripe 间距脚本检查：
     新间距 = P/4 − width > min spacing，sky130hd met4：
     6.785 − 1.6 = 5.185µm ≫ min spacing，必过）。
- **攻击者判据**（跑现有 `pg_infer.py`，零修改——测的就是朴素攻击者）：
  - 反推**崩溃**（pitch 断言失败，exit≠0），或
  - 恢复出**错误 pitch**（如 P/2 而非 P），误差 > 1% 即判防御成功；
  - 记录恢复的 offset/spacing 是否同步错乱。
- **防守者判据**：
  - `check_power_grid` 全网连通（PSM-0040）必须通过；
  - 电阻 mesh：worst-case 压降 **不差于** baseline（预期变好，金属多了）；
  - DRC clean。
- **对照组**：D1（同位置 decoy 但悬空/无 via）——预期反推**不受影响**
  （验证"via 连通性是 decoy 有效的必要条件"这一判断）。
- **估算成本**：ODB Tcl 脚本开发 ~半天；单次运行 < 1 min；
  mesh 求解 sky130hd/gcd 规模（~3000 节点）< 2 min。

### 实验 E2：pitch 抖动灵敏度曲线（D2）

- **对象**：sky130hd/gcd met4（单层先行）。
- **精确操作**：jitter 幅度 j ∈ {0, 2%, 5%, 10%, 15%} × pitch，
  每档随机种子 ×3；ODB Tcl 平移每条 stripe 及其 via 栈；
  扰动后检查相邻间距 ≥ min spacing（违例则重采样，记录重采样率）。
- **攻击者判据**：
  - j=0 对照：反推精确（已验证）；
  - 记录每档：反推是否崩溃；若把 TOL 放宽到 ±j 后重跑，
    恢复 pitch 与真 pitch 的相对误差 → 画"jitter-误差"曲线；
  - 顺带验证 RANSAC 版反推（~30 行，`--robust`  flag）在大 j 下
    仍能恢复近似值（诚实展示防御上限）。
- **防守者判据**：连通性 + DRC + mesh 压降退化 ≤ 5%
  （抖动不改变平均密度，预期退化极小）。
- **估算成本**：5 档 ×3 种子 = 15 次，每次 < 2 min；主要是脚本开发。

### 实验 E3：via 稀疏化打 connect（D4，对照性质）

- **对象**：sky130hd/gcd。
- **精确操作**：删除 p% 的 rail→strap via 栈，
  p ∈ {10%, 30%, 50%}（保留 strap→strap via）；
  或整段删除 met2-met3 span 的全部 via（链断裂）。
- **攻击者判据**：`pg_infer.py` 的 connect 输出与真值
  `{{met1 met4} {met4 met5}}` 对比——记录误判形式
  （多余对/缺失对/跳跃对）；并用误判配置做 roundtrip，
  几何 diff 定量差异。
- **防守者判据**：连通性必须保持（删多了会断网——这本身就是个
  "最大可删比例"测量点）；mesh 压降退化随 p 的曲线。
- **预期结论（先写下来，防 hindsight bias）**：
  connect 误判会被观测到，但 wire 参数反推不受影响——
  因此 D4 **不能独立作为防御**，只能量化"via 对推断的贡献度"。
  这个"负结果"本身值得写进论文（呼应 phase-5 的证伪风格）。
- **估算成本**：每次 < 2 min。

三实验的**统一输出**：每个 (design, 实验, 参数档) 生成
`defense_<exp>_<param>.json`（攻击者侧：反推 exit 码/恢复参数/误差；
防守者侧：连通性/DRC/mesh 压降），汇总成论文的 Figure/Table。

---

## 4. 诚实的风险与局限清单（写论文时必须面对的）

1. **没有商业级 IR-drop/EM signoff**（§2.1 已实证）。
   防守者判据只能到"连通 + DRC + 一阶电阻 mesh 对比"。
   Reviewer 一定会问："你怎么知道 decoy 网格不违反 EM？"
   诚实回答：标称电流密度 sanity check + 明确声明非 signoff；
   不能把 mesh 结果包装成"验证通过"。
2. **物理本身限制防御强度**。PDN 必须是低阻网格——欧姆定律决定了
   它"长得必然像 PDN"。D2 的 jitter 上限被 DRC spacing 卡死；
   D3 的 decoy 本质是"多加金属"，攻击者若知晓防御存在，
   可做子集枚举（N 小时暴力可行）。我们能 claim 的是
   **"显著提高朴素反推成本 / 引入不可辨识的意图歧义"**，
   不是"可证明安全"。任何信息论式的安全声明都是 oversell。
3. **自适应攻击者**（adaptive attacker）是主要威胁：
   - D1：via 连通性过滤，一行代码破解；
   - D2：RANSAC/鲁棒估计恢复近似参数（E2 会实测这条曲线）；
   - D3：已知 decoy 模式下的子集搜索；未知模式时仍是组合难题——
     这是 D3 相对最强的点，但要诚实标注边界。
   - 终极攻击者甚至可以**不反推参数**：直接把提取出的几何
     原样复制（clone）——PDN 没有"功能秘密"，只有"设计意图秘密"。
     论文必须明确：我们防的是**参数/规则提取**（设计 IP），
     不是物理复制（那是另一个威胁模型）。
4. **评估载体太小**。gcd/aes 是玩具设计；真实产品的 PDN 有 macro、
   多电压域、package 协同——我们的结论外推时要收敛。
   asap7 的双层 rail（M1+M2）已是一个提醒：PDK 差异会影响细节。
5. **pdngen 版本锁定**。全部结论基于 OpenROAD f12e2f47（2022）
   的 PdnGen.tcl；新版 pdngen（如支持 `define_pdn_grid` 的版本）
   行为可能不同，论文要写清版本。
6. **Defense 的 PPA 代价未量化**。D3 的布线阻塞、D2 对 detail route 的
   影响，需要跑完整 flow 到 route 才能量化——在 2 CPU/7.7GB 上可行
   （aes 除外可能较慢），列为后续工作，不要跳过不提。
7. **伦理表述**：attack 部分是"从自有版图恢复自有配置"
   （defensive research 的标准姿态）；论文中明确 responsible disclosure
   口径——我们发现的是**设计方法学**层面的信息泄露，不是某个产品的漏洞；
   且已同步向开源社区反馈死参数发现（如 `rails_start_with` 从未被读取，
   可提 OpenROAD issue）。

## 5. 建议的论文叙事线（供 parent 参考）

Attack（已完成，有硬数字）→ Defense 机制（E1/E2/E3，有曲线有对照）→
诚实讨论（§4）。标题级表述如
*"You Can't Hide a Power Grid (Easily): Reverse-Engineering and
Obfuscating PDN Grid Parameters from Layout Geometry"*。
Venue：HOST 2027（CFP 明确含 hardware reverse engineering / obfuscation）。
注意：不要把 D1 写成"有效防御"——它是被证伪的对照组，诚实写反而加分
（延续 phase-5 v_conn 证伪的风格，reviewer 吃这一套）。
