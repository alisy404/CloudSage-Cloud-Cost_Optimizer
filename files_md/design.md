# CloudSage Technical Design

## Approved technology stack

| Area               | Initial choice                  | Later option                                                              |
| ------------------ | ------------------------------- | ------------------------------------------------------------------------- |
|                    |                                 |                                                                            |
| Language           | Python 3.x                      | Keep core services Python                                                 |
| API                | FastAPI, Uvicorn                | Versioned API and UI gateway                                              |
| Validation/config  | Pydantic, pydantic-settings     | —                                                                         |
| AWS SDK            | boto3                           | —                                                                         |
| Database           | PostgreSQL                      | Managed PostgreSQL                                                        |
| ORM/migrations     | SQLAlchemy                      | Alembic                                                                   |
| Runtime AI         | One selected LLM API/provider   | Provider adapter permits replacement, not simultaneous runtime models     |
| HTTP               | httpx                           | —                                                                         |
| IaC                | Terraform CLI and JSON output   | Remote state and locking                                                  |
| Scheduling         | Simple jobs initially           | APScheduler/Celery plus Redis                                             |
| Containers         | Docker and Compose              | K3s                                                                       |
| UI                 | API/CLI first                   | React or Grafana                                                          |
| CI/CD              | GitHub Actions or Jenkins       | Never auto-apply production infrastructure                                |
| Quality            | pytest, ruff                    | Integration/evaluation suites                                             |
| Observability      | Structured logs initially       | OpenTelemetry, Prometheus, Grafana                                        |

## Repository file tree

```text
cloudsage/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/                 # routes and request orchestration
│   ├── domain/              # contracts, enums, domain models
│   ├── collectors/          # EC2, CloudWatch, Cost Explorer
│   ├── optimizers/          # plugin interface and EC2 optimizer
│   ├── ai/                  # provider, context, schema, validation
│   ├── terraform/           # mapping, generation, runner, plan policy
│   ├── policies/            # approval and safety decisions
│   ├── verification/        # baseline and post-change comparison
│   ├── db/                  # sessions, models, repositories
│   └── workers/              # scans and long-running jobs
├── tests/                   # unit, integration, evaluation, fixtures
├── terraform/               # controlled test infrastructure
├── scripts/                 # setup, data, and operational helpers
├── docs/                    # implementation documentation
├── .env.example
├── .gitignore
├── Dockerfile
├── compose.yaml
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Domain contracts

### Resource

`resource_id`, `service`, `resource_type`, `account_id`, `region`, `configuration`, `tags`, `terraform_mapping`, `observed_at`.

### Metrics observation

`resource_id`, `metric_name`, `window_start`, `window_end`, `average`, `p95`, `p99`, `maximum`, `sample_count`, `missing`, `source`, `observed_at`.

### Cost observation

`resource_id` or service scope, `period_start`, `period_end`, `amount`, `currency`, `dimension`, `attribution_quality`, `source`, `observed_at`.

### Candidate

`resource_id`, `candidate_type`, `rule_version`, `facts`, `missing_evidence`, `thresholds`, `created_at`.

### Recommendation

`recommendation_id`, `resource_id`, `optimization_type`, `decision`, `current_configuration`, `recommended_configuration`, `evidence`, `risk`, `confidence`, `estimated_monthly_savings`, `estimated_annual_savings`, `required_validation`, `status`, `created_at`.

## AI contract

The provider adapter exposes one application-level operation:

```python
analyze_optimization(context: OptimizationContext) -> RecommendationDraft
```

Structured response:

```json
{
  "decision": "recommend | reject | needs_more_data",
  "optimization_type": "rightsizing",
  "current_configuration": {},
  "recommended_configuration": {},
  "reasoning": [],
  "evidence": [],
  "concerns": [],
  "required_validation": [],
  "risk": "low | medium | high",
  "confidence": 0.0
}
```

The model may explain and interpret; backend code owns arithmetic, identifiers, policy, approvals, AWS calls, Terraform commands, and persistence.

## First EC2 rule

The first rule is conservative: the resource is running; sufficient history exists; average CPU is below a configured threshold; P95 and maximum CPU are below safety thresholds; no recent status-check failure, incident, or alert is present; and memory evidence is available or explicitly required as validation.

Output is `possible_rightsizing` with facts and missing evidence. The rule does not select a new type until pricing, compatibility, architecture, and policy checks support it.

## Deterministic savings

The savings engine receives current/proposed configurations, pricing source and timestamp, billing period, and assumptions.

```text
monthly_saving = current_monthly_cost - proposed_monthly_cost
annual_saving = monthly_saving * 12
```

The LLM can describe the result but cannot override it.

## API surface

```text
GET  /health
GET  /resources
GET  /resources/{resource_id}
POST /scans
GET  /scans/{scan_id}
POST /analysis/{resource_id}
GET  /recommendations
GET  /recommendations/{id}
POST /recommendations/{id}/approve
POST /recommendations/{id}/reject
POST /terraform/{id}/plan
POST /terraform/{id}/apply
GET  /optimizations/{id}/verification
GET  /audit
```

Analysis, approval, planning, and apply remain separate endpoints and state transitions.

## Database entities

`resources`, `resource_metrics`, `cost_records`, `terraform_resources`, `optimization_candidates`, `recommendations`, `terraform_plans`, `approvals`, `verification_results`, `audit_logs`, and later `optimization_runs`.

## Configuration and secrets

`.env.example` contains names only. Local secrets come from the environment or supported AWS credential providers. Production secrets come from a secret manager. Never log or send AWS keys, LLM keys, database passwords, Terraform state secrets, or raw credential material to the model.
