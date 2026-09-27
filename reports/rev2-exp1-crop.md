# 实验 1：局部裁剪外推（rev2 / A1）

日期：2026-09-27 PDT · 脚本：`/tmp/rev2/a1/run_a1.py` · 结果：`/tmp/rev2/a1/report.json`

设计：sky130hd/gcd。裁剪语义 = **形状接触观察窗口**（via：中心在窗口内；
stripe/rail：网格轴中心在窗口内且矩形在另一轴与窗口相交）。注意这模拟的是
**带 net/layer/shape 标签的 ODB 裁剪**，不是无标签成像多边形——后者仍是
威胁模型缺口，保留为 future work。

## 结果

### 1. 10% 左侧竖条（全高度，~10% die 面积）

窗口内：met5 VDD/VSS 各 9 条；met4 VDD 1 条、VSS 0 条。

- met5：width 1.600 µm、pitch 27.200 µm、offset 13.600 µm，全部 exact
- met4：pitch 不可辨识（同 net 同层不足 2 条）
- connect 仍恢复为 `{met1 met4} {met4 met5}`，starts_with = POWER
- met5 全 die 外推 exact；**全 die 重生成 FAIL**——原因是观察窗只含 1 条
  met4/VDD 且无 met4/VSS，信息不足，不是数值误差。

### 2. 20% 左侧竖条

窗口内：met4 VDD 2 条、VSS 1 条；met5 VDD/VSS 各 9 条。

- met4 width/pitch/offset = 1.600 / 27.140 / 13.570 µm，逐项 exact
- met5 width/pitch/offset = 1.600 / 27.200 / 13.600 µm，逐项 exact
- connect、starts_with 全部 exact
- 四组 `(layer, net)` stripe-center 全 die 集合全部 exact → **PASS**

### 3. ~10% 面积左下角方形（~0.316W × 0.316H）

窗口内：met4/met5 × VDD/VSS 各 3 条。所有参数、connect、starts_with
全部 exact，四组 stripe-center 全 die 集合全部 exact → **PASS**

## 结论

- 不能说"任意 10% 裁剪即可恢复"：10% 细长竖条因横向（met4）采样不足失败，
  而同面积的方形裁剪成功、20% 竖条成功。
- 准确表述：**局部恢复取决于裁剪形状及每层每 net 是否观察到足够多的周期
  实例**（本设计中每组 ≥2–3 条即足够）。
- 本实验支持在论文中增加局部外推实证，但不改变"无标签成像多边形尚未处理"
  的威胁模型声明。
