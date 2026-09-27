# Issue 3 语义核查：pdngen `connect` 的跨层行为（rev2 / B1）

日期：2026-09-27 PDT · 实验：`/tmp/rev2/pdn/b1_conn*/`、`cfgs/conn_*.tcl`

## 结论先行

1. **"只有相邻 grid layer 才能连接"是错误的。** pdngen 的 `connect` pair 可以跨越多个 routing layer 并生成连续 via stack——asap7 的 `{M1 M5}` 真值就是直接证据（M1→M2→M3→M4→M5 四段 span 全有 via）。
2. 连接成功与否不由层号是否"相邻"决定，而由 pair 两端实际网格形状在交点的几何 overlap 决定：正交相交（H×V）能生成完整 via stack；平行窄 rail 与宽 stripe 的 overlap 不足以覆盖上层宽度时触发 PDN-0042 全部跳过。
3. 推断器把 via-span 链折叠为 connect 对的逻辑是正确的（asap7 链 M1→…→M6 折叠为 `{M1 M5} {M5 M6}`），论文 §3.3 对 connect 的描述需要按本报告修正。

## 实测事实

### asap7（真值 connect = `{{M1 M5} {M5 M6}}`）

实际 via span：M1-M2/M2-M3/M3-M4/M4-M5 各 106，M5-M6 8。推断器将链
M1→M2→M3→M4→M5→M6 折叠为 `{{M1 M5} {M5 M6}}`。

方向：M1 FOLLOWPIN:H、M2 FOLLOWPIN:H、M5 STRIPE:V、M6 STRIPE:H。
M2 虽然也是 rail layer，但在 M1→M5 的 via stack 中是**中间层**，不是 connect
的最低 endpoint——推断器按"连通 via-span 链的最低 rail endpoint → 其上第一
strap endpoint"选 M1→M5，随后连接连续 strap endpoints M5→M6。

### sky130hd/gcd 对照实验（只改 stdcell connect，macro grid 保留）

| connect | wires | vias | 结果 |
|---|---|---:|---|
| `{{met1 met4}}` | 133 | 2736 | met1→met4 完整三段栈（912×3）|
| `{{met4 met5}}` | 133 | 171 | 仅 met4-met5 |
| `{{met1 met5}}` | 133 | 0 | PDN-0042 全部跳过 |
| `{{met1 met4} {met1 met5}}` | 133 | 2736 | met1→met4 成功，met1→met5 全部跳过 |

sky130 方向：met1 FOLLOWPIN:H、met4 STRIPE:V、met5 STRIPE:H。

### 机制解释

- `{met1 met5}` 失败不是因为"层不相邻"，而是因为 met1（H）与 met5（H）**平行**：
  窄 met1 rail 与宽 met5 stripe 的 overlap 不足以覆盖 met5 宽度，触发
  "No via added … because the full height of met5 (1.6) is not covered by the overlap"（PDN-0042）。
- met1（H）与 met4（V）正交相交 → met1→met4 完整栈成功。
- asap7 M1（H）与 M5（V）正交相交 → `{M1 M5}` 生成 M1→M5 完整四段栈。
- 因此判据是**几何 overlap**，不是层号距离。

## 对论文的修改建议（写作时用，不在本任务改 tex）

- §3.3 "connect 只能连接相邻 grid layer" 改为：connect pair 可跨越多个
  routing layer；能否生成 via 取决于两端网格在交点的几何 overlap（正交相交
  通常成功，平行窄-宽相交可能触发 PDN-0042 跳过）。
- 补充 asap7 `{M1 M5}` 作为跨层证据，以及 sky130 `{met1 met5}` 0-via 作为
  反例；说明推断器的"最低 rail endpoint → 第一 strap endpoint"折叠规则。
