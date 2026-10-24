# 架构与模块边界

## 1. 分层

```
┌─────────────────────────────────────────────────────────────┐
│ API (FastAPI)                    CLI (iatp)                 │
├─────────────────────────────────────────────────────────────┤
│ Services   run / baseline / regression / report / seed      │
├─────────────────────────────────────────────────────────────┤
│ Orchestration   runner · artifact writer                    │
├──────────────────────────────┬──────────────────────────────┤
│ Evaluation                   │ Report                       │
│ checks · metrics · regression│ generator · service          │
│ evidence · hashing           │                              │
├──────────────────────────────┴──────────────────────────────┤
│ Adapters        mock · http_json                            │
├─────────────────────────────────────────────────────────────┤
│ Simulation      process · faults · interlocks · safety      │
├─────────────────────────────────────────────────────────────┤
│ Core            models · domain · catalog · units · hashing │
└─────────────────────────────────────────────────────────────┘
```

依赖只能向下：`api/cli → services → orchestration → evaluation/simulation/adapters → core`。
`evaluation` 不导入 `ProcessSimulator` 或 `SafetyGate` 的具体实现，只消费
`CaseRunEvidence` 与领域契约；`adapters` 不含评测逻辑。

## 2. 关键对象

| 对象 | 位置 | 职责 |
|---|---|---|
| `DomainPack` | `core/domain.py` | 位号、边界、推荐区间、联锁表、故障库、过程模型 |
| `ProcessSimulator` | `simulation/process.py` | 确定性过程推进、测量、采样、观测窗口 |
| `SafetyGate` | `simulation/safety.py` | 权限 → 工艺边界 → 确认 → SIS → DCS 顺序门禁 |
| `InterlockEngine` | `simulation/interlocks.py` | 独立联锁求值，不读取 Agent 建议 |
| `CaseRunEvidence` | `evaluation/evidence.py` | 判定所需的只读证据视图 |
| `RunRecord` | `core/models.py` | 运行、用例结果、指标、指纹与报告路径 |
| `PlatformContext` | `services/context.py` | 目录、目录表、仓储、服务装配 |

## 3. 一次运行的写入路径

1. `RunService` 解析套件、用例与 Agent，分配种子。
2. `runner` 为每个用例创建目录，写入 `case.yaml` 与 `manifest.json`。
3. 仿真推进，按决策间隔调用 Agent，记录原始请求/响应。
4. 每条控制请求送入 `SafetyGate`；门禁写出 `gate_decisions.json` 与 `action_trace.json`。
5. `evaluation.checks` 读取证据，产出缺陷；`metrics` 聚合指标。
6. `run_service` 执行复现校验，写入 `non_reproducible`（如失败）。
7. 仓储保存运行、指标、缺陷、指纹；报告服务按需生成 Markdown。

## 4. 数据与证据目录

```
data/iatp.db                         运行、基线、回归、报告索引
artifacts/runs/<run_id>/
  report.md                          Markdown 报告（按需生成）
  <case_id>/
    case.yaml
    series.csv
    agent.json
    verdict.json                     含缺陷、机理校验与联锁评估
    fingerprint.txt
    gate_decisions.json
    actions.jsonl
    injection.json
    manifest.json                    用例种子、指纹与文件清单
    responses/call-0001.json ...
```

所有物理量在边界处显式携带单位；相对时间使用 float 秒，墙钟时间使用带时区 ISO 8601。

## 5. API 与前端

- FastAPI 暴露 `/api/*`；无联锁修改、旁路或 DCS 直写端点。
- 生产模式下，若 `frontend/dist` 存在，FastAPI 以 SPA fallback 托管静态资源。
- 前端为 React 18 + TypeScript + Vite，路由覆盖总览、运行、用例、安全、回归、报告。
- 图表为自绘 SVG：每测点独立小图、不使用双轴、附可访问数据表；看板先披露数据构成，
  再展示漏报率与 P0。

## 6. 确定性与安全不变量

- 过程随机数、采样噪声、链路抖动与调用种子全部由显式种子派生。
- `SafetyGate` 先写 `GATE_ALLOWED`，再调用 DCS；被阻断的请求不会触达 DCS 回调。
- 联锁引擎独立于 Agent 与用例；用例不能关闭联锁。
- 结论指纹只覆盖结构化语义，回归不比较自然语言。
- 基线/回归要求用例集、领域包、联锁表三项哈希一致，否则拒绝比较。

## 7. 部署形态

- 本地：`iatp serve` 或 `make dev`，前端可用 Vite 开发服务器。
- 单容器：多阶段 Docker 构建前端后由 FastAPI 托管，SQLite 与证据目录挂载卷。
- CI：`pytest` + `ruff` + `mypy` + `npm run typecheck` + `npm run build`。
