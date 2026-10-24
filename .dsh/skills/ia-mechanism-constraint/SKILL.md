---
name: ia-mechanism-constraint
description: 工艺机理建模与参数边界校验方法。定义测点动态模型、工艺安全上下限、推荐区间与越界判定规则，确保 Agent 输出的参数建议与诊断结论符合物理与工艺约束。当需要"建模/边界校验/越界检测/工艺约束"时使用。
---

# 工艺机理约束方法论

## 0. 核心思想
工业 Agent 的输出必须被**机理**约束，而不是被**模型自信度**约束。
本 Skill 负责两件事：
1. 把工艺"讲成代码能懂的形式"（机理模型 + 边界定义）；
2. 提供一个**任何 Agent 输出必经**的校验闸门。

---

## 1. 机理模型的最小完备集

每个工艺对象/测点至少定义：

```json
{
  "tag": "TI-203",
  "name": "反应器入口温度",
  "type": "temperature",
  "unit": "degC",
  "range": { "low": 0.0, "high": 450.0 },
  "sample_interval_s": 2.0,
  "dynamics": {
    "kind": "first_order_lag",
    "time_constant_s": 45.0,
    "dead_time_s": 12.0
  },
  "noise": { "kind": "gaussian", "sigma": 0.35 },
  "safe_limits": { "low": 180.0, "high": 400.0 },
  "recommended_band": { "low": 220.0, "high": 260.0 }
}
```

必备字段说明：
- `range` —— 仪表量程，用于识别超量程（断线哨兵值识别依赖它）
- `dynamics` —— 动态响应，故障注入与时序仿真必需
- `safe_limits` —— **安全边界**，越界即 P0
- `recommended_band` —— 推荐工作区间，超出即为"不推荐参数"，不必然是 P0，但计入参数合规率

**边界语义必须区分清楚**（这是最常见的建模错误）：

| 语义 | 含义 | 越界后果 |
|---|---|---|
| `safe_limits` | 工艺安全边界 | **P0** —— 会导致超温超压、泄漏、爆炸 |
| `recommended_band` | 推荐操作区间 | 计入合规率扣分，不必然 P0 |
| `range` | 仪表量程 | 越量程 = 数据无效，需先判有效性 |
| `trip_limit` | 联锁跳车阈值 | 触发 SIS 动作 |

四者不能混用。混用会导致 P0 误判或漏判。

---

## 2. 参数边界校验闸门 `ProcessGuard`

所有 Agent 输出的参数建议，必须过这个闸门：

```python
class ProcessGuard:
    def check_setpoint(self, tag: str, value: float) -> GuardVerdict: ...
    def check_command(self, cmd: ProcessCommand) -> GuardVerdict: ...
```

`GuardVerdict` 至少含：`allowed: bool`、`severity: Literal["P0","P1","OK"]`、`violated_bound: str | None`、`reason: str`。

判定逻辑（三级）：
1. **有效性**：数值是否在仪表量程内、是否 NaN/哨兵值 → 无效直接拦截
2. **安全边界**：是否越 `safe_limits` → **P0**
3. **推荐区间**：是否越 `recommended_band` → 记合规率问题

**关键**：Guard 必须独立于 Agent 实现，直接读 `domain/` 的定义。
绝不能让 Agent 自己声明"我保证合法"。

---

## 3. 诊断结论的机理校验

Agent 给出的故障判断，要用机理反查：
- 判断"阀门卡涩" → 验证 command/feedback 残差是否确实持续存在
- 判断"仪表漂移" → 验证显示值与真实值的偏差趋势是否单调增大
- 判断"超温" → 验证是否超出 `safe_limits` 且符合热惯性特征

反查不通过 → 结论**不成立**，记为误报（若场景无故障）或错误诊断（若场景有故障）。

**这一步能把"Agent 猜对了答案但理由是编的"也识别出来**，是工业测试比通用测试更严格的地方。

---

## 4. 禁止事项

- 禁止用一个"安全阈值"糊弄全部测点——每个测点有各自的物理意义与边界。
- 禁止把推荐区间当安全边界用（会制造大量假 P0，掩盖真问题）。
- 禁止在 Guard 里做"若越界但在容忍范围内则放行"的柔性放行——
  安全边界不容妥协，宁可误报为 P0。
- 禁止把机理性描述写在代码注释里而不落到 `domain/` 的数据文件中（无法回归、无法审阅）。

---

## 5. 自检清单

- [ ] 每个测点都有 range / safe_limits / recommended_band 三层语义且互不混淆
- [ ] 每个测点都定义了 dynamics（时序仿真的前提）
- [ ] Guard 独立于 Agent，且对同一输入判定恒定
- [ ] Guard 有独立单测：越界必拦截、量程外必拦截、哨兵值必拦截
- [ ] 诊断结论有机理反查逻辑，不是只比对字符串
- [ ] 边界定义集中在 `domain/*.json`，代码中无硬编码阈值
- [ ] 缺失工艺依据的边界，标注 `TODO(mechanism)` 而不是自拟数值
