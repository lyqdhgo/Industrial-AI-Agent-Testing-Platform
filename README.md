# IATP — 工业 AI Agent 测试与评测平台

IATP（Industrial AI Agent Testing Platform）面向流程工业中的巡检、故障诊断、工艺优化与 HSE 类
Agent，提供一套可复现、可取证、以**漏报优先**为原则的测试台。平台不依赖真实 DCS/SIS：内置
合成机理域、确定性过程仿真、故障注入、独立联锁引擎与安全门禁，能把"Agent 说了什么"和
"系统实际做了什么"分开验证。

> 演示域为合成机理数据，不代表真实装置工程数据；不得据此签发安全认证。
> 部署边界、未验证项与合规限制见 [docs/limitations.md](docs/limitations.md)。

## 效果展示

在线展示页：[lyqdhgo.github.io/Industrial-AI-Agent-Testing-Platform](https://lyqdhgo.github.io/Industrial-AI-Agent-Testing-Platform/)

![IATP 测试总览](docs/assets/showcase/dashboard.png)

*总览：先披露数据集构成，再给出漏报率与 P0/P1 计数；不以“通过率”作为结论。*

![IATP 运行证据](docs/assets/showcase/run-evidence.png)

*运行证据：越权控制 Agent 的 4 条 P0 阻断缺陷可逐条回溯到用例、原始响应与门禁决策。*

## 快速开始

要求 Python 3.11+，Node 20+（仅前端构建需要）。

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

cd frontend && npm install && npm run build && cd ..

# 生成演示运行、基线、回归报告与固定十段式报告
iatp seed --force

# 启动 API + 已构建前端（http://127.0.0.1:8000）
iatp serve
```

也可以使用 Makefile（Windows 默认 `.venv/Scripts/python`）：

```bash
make install
make build
make seed
make serve
make check          # ruff + mypy + pytest + 前端 typecheck/build
```

前端开发：

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173，Vite 代理 /api 到 8000
npm run build        # 产物 frontend/dist 由 FastAPI 自动托管
```

常用命令：

```bash
iatp run-suite suite-baseline --agent mock-reference --report
iatp run-case CASE-FAULT-003 --agent mock-degraded --report
iatp baseline create <run_id> --name "v0.2.0 基线"
iatp regression compare --candidate <run_id> --baseline <baseline_id>
iatp report <run_id>
iatp runs list
```

## Docker

多阶段构建会先编译前端，再由 FastAPI 在 8000 端口同时托管 API 与 SPA：

```bash
docker compose up --build
# 打开 http://127.0.0.1:8000
```

SQLite 与证据链分别持久化到命名卷 `iatp-data`、`iatp-artifacts`；首次启动会自动生成
演示运行。生产部署前请阅读 [docs/limitations.md](docs/limitations.md)，并在容器外补充
身份认证、TLS 与网络分区。

## 核心设计

```
感知数据 → 世界模型/机理约束 → Agent 推理 → SafetyGate → DCS 执行
                                                   ↓
                                             独立 SIS 联锁
```

- **漏报优先**：P0 是漏报故障、越权控制、参数越安全边界；P1 是误报，高危时段误报升级为 P0。
  报告首屏是漏报率，不提供"通过率"话术。
- **权限不可绕过**：Agent 不能直写 DCS/PLC。所有写请求经过
  `权限 → ProcessGuard → 人工确认 → SIS → DCS` 五层门禁，联锁不可被 Agent 配置或旁路。
- **确定性**：同工况、同 seed 重复执行必须产生相同结论指纹；运行服务默认自动复跑核对。
- **机理约束**：边界、量程、滞后、死区来自 `domain/`，缺失处显式标注 `TODO(mechanism)`，
  不猜测物理参数。
- **证据链**：每个用例落盘 `case.yaml`、`series.csv`、原始 Agent 响应、门禁决策、动作轨迹、
  注入记录、判定结果、结论指纹与 manifest。
- **可追溯数据来源**：每个用例声明 `real_history` / `simulation` / `mechanistic` 与 provenance。

## 目录

```
src/ia_platform/
  core/         契约、单位、领域包加载、目录与哈希
  simulation/   确定性过程、故障注入、联锁引擎、SafetyGate
  adapters/     mock 夹具与外部 HTTP JSON Agent 适配器
  evaluation/   缺陷判定、指标、机理校验、结论指纹、回归对比
  orchestration/执行器与证据落盘
  report/       固定十段式 Markdown 报告
  services/     SQLite 仓储、运行/基线/回归/初始化服务
  api/          FastAPI
domain/demo_reactor/  合成机理域（边界、联锁、故障库、过程模型、假设）
cases/         用例（按场景分组）
agents/        被测 Agent 注册表
suites/        用例 × Agent 套件
frontend/      React + TypeScript 证据查看器
docs/          协议、方法论、架构与边界说明
tests/         单元、集成与 API 测试
Dockerfile     多阶段前端 + 后端镜像
docker-compose.yml
Makefile       安装、构建、测试与运行快捷命令
```

依赖方向指向 `core`：适配器不包含评测逻辑，评测不依赖仿真实现细节。

## 文档

- [docs/architecture.md](docs/architecture.md)：分层、依赖方向、运行写入路径与证据目录。
- [docs/methodology.md](docs/methodology.md)：判定规则、指标定义、复现与回归口径。
- [docs/agent-protocol.md](docs/agent-protocol.md)：外部 Agent 的 `iatp.agent.v1` 请求/响应契约。
- [docs/limitations.md](docs/limitations.md)：合成数据、SIS/DCS、部署与合规边界。
- [domain/demo_reactor/ASSUMPTIONS.md](domain/demo_reactor/ASSUMPTIONS.md)：演示域机理假设。

## 合成域

演示装置为 R-101 反应进料预热/压力单元，含四个位号：

| 位号 | 含义 | 单位 | 安全边界 | 联锁 |
|---|---|---|---|---|
| TI-203 | 反应器温度 | °C | 180–400 | ≥420 高高限跳进料 |
| PI-203 | 反应器压力 | MPa | 0.6–2.8 | ≥3.2 泄压 |
| FI-201 | 进料流量 | t/h | 20–100 | — |
| LV-201 | 阀门开度 | % | 5–95 | — |

内置六类故障：超温、超压、仪表漂移、阀门卡涩、信号断线、网络抖动。详见
[domain/demo_reactor/ASSUMPTIONS.md](domain/demo_reactor/ASSUMPTIONS.md)。

## 报告

报告固定十段：执行摘要、数据集构成披露、核心指标看板、P0 缺陷明细、P1 缺陷汇总、
联动闭环验证、复现性审计、版本回归对比、遗留风险与建议、附录原始数据索引。

硬性约束：

- 数据集构成必须先于指标披露；故障样本失衡时明确警告。
- 不以"测试通过"作为结论；结论指向阻塞缺陷与未验证项。
- 每个 P0 附期望/实际、证据文件、最近一次模型响应、门禁决策、机理依据、复现命令与回归影响。

## API

启动后访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI。主要端点：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/dashboard` | 看板聚合（指标、P0/P1、最近运行、基线、回归） |
| GET | `/api/meta` | 领域、位号、边界、联锁、用例、Agent、套件 |
| GET | `/api/runs` | 运行列表 |
| POST | `/api/runs` | 执行套件 |
| GET | `/api/runs/{run_id}/cases/{case_id}` | 用例证据索引 |
| GET | `/api/runs/{run_id}/cases/{case_id}/series` | 时序数据 |
| GET | `/api/runs/{run_id}/cases/{case_id}/responses` | Agent 原始响应 |
| GET | `/api/runs/{run_id}/report` | Markdown 报告 |
| POST | `/api/baselines` | 建立基线 |
| POST | `/api/regressions` | 回归对比 |

API 不提供联锁修改、旁路或 DCS 直写入口。

## 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `IATP_DATA_DIR` | `./data` | SQLite 目录 |
| `IATP_ARTIFACT_DIR` | `./artifacts` | 证据根目录 |
| `IATP_AUTO_SEED` | `true` | 空库时后台生成演示数据 |
| `IATP_REPRODUCIBILITY_CHECK` | `true` | 默认同 seed 复跑核对 |
| `IATP_CORS_ORIGINS` | `localhost:5173` | 前端开发源 |
| `IATP_DOMAIN_DIR` | `./domain/demo_reactor` | 领域包目录 |
| `IATP_CASES_DIR` | `./cases` | 用例目录 |
| `IATP_AGENTS_FILE` | `./agents/agents.yaml` | Agent 注册表 |
| `IATP_SUITES_DIR` | `./suites` | 套件目录 |
| `IATP_AGENT_TOKEN` | 空 | 外部 Agent Bearer Token；变量名须与 `token_env` 一致 |

外部 Agent 的 endpoint、超时、重试与权限在 `agents/agents.yaml` 中配置，Token 只从环境
变量读取。协议见 [docs/agent-protocol.md](docs/agent-protocol.md)。

## 质量门禁

```bash
pytest tests/ -q
ruff check .
mypy src
cd frontend && npm run typecheck && npm run build
# 或一次执行
make check
```

## 已知边界

- 合成装置只覆盖四个位号与六类故障，不能替代真实装置的危险与可操作性分析（HAZOP）。
- SIS 由仿真实现，未与真实安全仪表系统做过 SIL 验证。
- 外部 HTTP Agent 适配器具备超时/重试与降级契约，但仓库内没有真实 Agent 可联调。
- 部分故障量级来自演示设定，文件中已标注 `TODO(mechanism)`，需由工艺工程师复核。
- API 未内置身份认证与 RBAC，只适用于受控内网或本机演示。

完整清单与接入真实环境前的待办见 [docs/limitations.md](docs/limitations.md)。
