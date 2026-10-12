# CloudSage Project Memory

This file is durable context for future development sessions. Update it when a decision, milestone, or project state changes.

## Identity

- **Project:** CloudSage
- **Purpose:** AI-powered AWS infrastructure cost optimization
- **Current state:** Stage 0, 1, 2, 3 complete. Stage 4 (deterministic analysis) is next.
- **Initial service:** EC2
- **Initial optimization:** rightsizing/underutilization
- **Initial interface:** Server-rendered Jinja2 + HTMX dashboard (FastAPI backend)

## Non-negotiable decisions

- Multiple AI tools can assist during development.
- Runtime uses exactly one selected LLM provider/API key.
- Runtime is not multi-agent in the initial product.
- AI recommends; deterministic backend code validates and controls execution.
- Financial calculations are deterministic and independently reproducible.
- Terraform is the preferred infrastructure change mechanism.
- Human approval is required before infrastructure changes.
- The initial AWS role is read-only; no unrestricted write access is given to the LLM.
- Fail closed for incomplete evidence, invalid output, policy failure, unexpected Terraform plans, missing approval, or provider failure.

## Current target milestone

Stage 2 — Real EC2 discovery:

- `app/config.py` — pydantic-settings, AWS_MODE toggle, AWS_REGION, APP_ENV
- `app/aws/ec2.py` — `EC2Client` interface + `BotoEC2Adapter` + `FakeEC2Adapter`
- `app/models.py` — `EC2Instance` Pydantic model
- `app/main.py` — switch between fake/real adapter based on AWS_MODE env var
- Unit tests in `tests/unit/aws/` with mocked boto3

Required AWS permissions (read-only):
- `ec2:DescribeInstances`
- `ec2:DescribeTags`
- `sts:GetCallerIdentity`

This milestone must not apply infrastructure.

## Planned progression

| Version | Scope |
|---|---|
| V0 | EC2 discovery, basic metrics/cost, CLI/API, no AI, no writes |
| V1 | PostgreSQL normalization, trends, deterministic candidates, savings |
| V2 | One-provider structured AI recommendations and validation |
| V3 | Terraform state mapping, code context, plan generation and parsing |
| V4 | Human approval, policy engine, audit, role separation |
| V5 | Controlled Terraform apply and rollback |
| V6 | Post-optimization verification and realized savings |
| V7 | More AWS services |
| V8 | Dependency-aware optimization |
| V9 | Production platform: UI, workers, scheduling, RBAC, multi-account |
| V10 | Historical intelligence, RAG, natural language, evaluation, optional automation |

## Expected first stack

Python, FastAPI, Uvicorn, Pydantic, pydantic-settings, boto3, SQLAlchemy, PostgreSQL, httpx, pytest, ruff, Docker/Compose, Terraform, and one runtime LLM API/provider. APScheduler/Celery, Redis, React/Grafana, K3s, OpenTelemetry, Prometheus, and RAG are later additions.

## Inputs and outputs

Inputs include resource metadata, cost, CloudWatch aggregates, health/alerts, Terraform state/code/plan, history, environment, criticality, and SLA/SLO context.

Outputs include a decision, optimization type, current/proposed configuration, evidence, risk, model confidence, deterministic monthly/annual savings, concerns, required validation, Terraform impact, status, and audit events.

## Known risks

- AWS cost attribution may be approximate.
- CPU averages hide spikes and memory may be missing.
- Model confidence is not truth.
- Logs/tags/commit text may contain prompt injection.
- Terraform drift and dependencies can make a change unsafe.
- AWS APIs throttle and cost data can lag.
- Predicted savings can differ from realized savings.
- The optimizer itself has AWS, database, and LLM costs.
- Scope can expand too quickly; preserve the staged version plan.

## Reference documents

- `CloudSage_Project_Documentation/01_project_description.docx` — purpose and scope
- `CloudSage_Project_Documentation/02_architecture.docx` — architecture and data flow
- `CloudSage_Project_Documentation/03_build_from_first_command.docx` — original runbook
- `CloudSage_Project_Documentation/04_project_versions.docx` — version plan
- `CloudSage_Project_Documentation/05_problems_and_risks.docx` — risks
- `CloudSage_Project_Documentation/06_aftercare_operations.docx` — aftercare
- `CloudSage_Project_Documentation/07_ai_design.docx` — runtime AI boundary
- `CloudSage_Project_Documentation/08_apis_data_contracts.docx` — APIs and entities
- `CloudSage_Project_Documentation/09_security_testing.docx` — security and testing
- `CloudSage_Project_Documentation/10_roadmap_and_future.docx` — expansion roadmap
- `CloudSage_Project_Documentation/11_project_index_and_decisions.docx` — central decisions

## Session update format

```text
Date:
Current version/stage:
Completed:
Verification run:
Failures or risks:
Next task:
Decision changes:
```
