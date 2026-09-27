# B3：鲁棒拟合替换 2-dbu 众数断言（rev2）

日期：2026-09-27 PDT

## 改动

`src/pg_infer.py`（及 defense 的逻辑拷贝 `defense/pg_infer_def.py` 已同步）：

- 旧：`p = Counter(round(x) for x in diffs).most_common(1)[0][0]` +
  `assert max(abs(x-p)) <= 2 dbu`（相邻差众数投票，对数值噪声脆弱）。
- 新：`ls_fit(cs)` 最小二乘拟合 `c_i = c0 + i·p`（indices 连续假设），
  `p = round(p_est)`；残差门 `assert resid <= 2 dbu` 保留。

设计意图：估计器换成最小方差的 LS（§7.2 鲁棒攻击同款），容忍亚 dbu
数值噪声；残差门仍拒绝真正的多模态（诱饵交织）网格——朴素攻击者在
混淆输入上保持大声失败，E1 的 defense 结论不受影响。

## 验证

- 4 个设计重跑反推：`pdn_inferred.cfg` **字节一致**（sky130hd/gcd、
  nangate45/gcd、sky130hd/aes、asap7/gcd）。
- 4/4 round-trip：反推配置重跑 pdngen，wire 矩形 + via 集合对称差全 0
  （含 16,721 行的 aes）。**4/4 PASS**。
- E1a 上朴素攻击者仍失败：`AssertionError: non-uniform pitch met4 VDD:
  LS pitch 13570.0 dbu, max residual 3571.1 dbu > 2 dbu`（exit 1）。
  错误信息比原来更具诊断性。
- 说明：更大的 placement jitter（E2 场景）仍走 §7.2 的自适应 LS 路径；
  主工具的 2-dbu 门只保证"精确等差"假设，不默默接受多模态输入。
