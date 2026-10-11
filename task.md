# CloudSage Development Tasks

This is the current implementation plan for the first working CloudSage application.

The goal is to build one small, complete vertical slice before adding the larger platform features described in the other project documents.

## Current MVP goal

Open a web application, select an EC2 instance, read its AWS metadata and CloudWatch metrics, send bounded evidence to one configured LLM provider, display an explainable rightsizing suggestion, generate a Terraform change/diff, and require human approval before any Terraform action.

Initial workflow:

```text
Browser UI
  -> FastAPI backend
  -> read-only AWS APIs
  -> EC2 metadata + CloudWatch metrics
  -> deterministic metric checks
  -> one runtime LLM provider
  -> validated recommendation
  -> Terraform change/diff
  -> human approval
```

The first MVP does not automatically apply infrastructure.

## 1. Current technology stack

| Area | Technology | Why it is used now |
|---|---|---|
| Language | Python 3.x | Fast implementation and strong AWS ecosystem |
| Backend | FastAPI + Uvicorn | Small API with automatic OpenAPI documentation |
| UI | Jinja2 templates + HTMX + plain CSS | Simple server-rendered UI without a separate frontend build system |
| AWS SDK | boto3 | EC2 and CloudWatch access |
| AWS data | EC2 API + CloudWatch API | First resource and metric source |
| AI | One selected LLM API/provider through an adapter | Runtime must use one provider/API key |
| Validation | Pydantic | Settings, API data, and AI output validation |
| HTTP client | httpx | Provider adapter and test mocking |
| Terraform | Terraform CLI and generated diff | Infrastructure change proposal and later plan validation |
| Initial storage | In-memory objects plus local JSON files | Keeps the first working slice small |
| Later storage | SQLite, then PostgreSQL | Add persistence after the workflow works |
| Testing | pytest, pytest-asyncio, mocks/fixtures | Fast unit and API tests without requiring AWS |
| Quality | ruff | Linting and formatting checks |
| Packaging | Python virtual environment | Reproducible local development |
| Containerization | Docker later | Add after local workflow is stable |

The following are intentionally postponed: React, PostgreSQL, Redis, Celery, Kubernetes/K3s, multi-account support, authentication, multiple runtime models, multi-agent AI, automatic apply, and additional AWS services.

## 2. Target first repository structure

```text
cloudsage/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── routes.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── instance.html
│   │   └── recommendation.html
│   ├── static/
│   │   └── styles.css
│   ├── aws/
│   │   ├── ec2.py
│   │   └── cloudwatch.py
│   ├── analysis/
│   │   ├── metrics.py
│   │   ├── candidate.py
│   │   └── savings.py
│   ├── ai/
│   │   ├── provider.py
│   │   ├── context.py
│   │   ├── schemas.py
│   │   └── service.py
│   └── terraform/
│       ├── diff.py
│       └── validation.py
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── api/
├── terraform/
│   └── examples/
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

## 3. Development rules for this MVP

- Use one AWS resource family: EC2.
- Use read-only AWS permissions only.
- Use one runtime LLM provider/API key.
- Keep development AI tools separate from runtime AI.
- Never send AWS credentials or secrets to the LLM.
- Never let the LLM execute shell commands, AWS calls, or Terraform commands.
- Deterministic Python code calculates metric summaries and savings.
- The LLM explains evidence and proposes a change; it does not make the final safety decision.
- Do not silently treat missing metrics as zero.
- Do not automatically apply Terraform.
- Show the proposed Terraform change and require explicit approval.
- Keep AWS-dependent behavior behind interfaces so tests can run offline.

## 4. Stage 0 — Prepare the workspace

### Build first

1. Create the Python virtual environment.
2. Add the application and test directories from the target tree.
3. Add dependency and configuration files.
4. Add a minimal FastAPI application.
5. Add a placeholder test.

Recommended dependencies:

```text
fastapi
uvicorn[standard]
jinja2
python-multipart
boto3
pydantic
pydantic-settings
httpx
pytest
pytest-asyncio
ruff
```

### Commands

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Test before continuing

```bash
pytest
ruff check .
curl http://localhost:8000/health
```

Expected result: the server starts, `/health` returns a successful response, and the placeholder test passes.

## 5. Stage 1 — Build the empty app and simple UI

### Build first

1. Create the FastAPI application entry point.
2. Add Jinja2 template configuration.
3. Add a base layout and a dashboard page.
4. Add simple CSS for readable cards, tables, status labels, and buttons.
5. Add an HTMX endpoint that can replace the instance list on the page.
6. Use fake instance data at this stage.

### UI at this stage

The dashboard should show an application name, environment, fake EC2 instances, instance ID, name/tag, type, state, region, and a button to open an instance details page.

### Test

Automated:

```bash
pytest tests/api
```

Manual:

1. Start Uvicorn.
2. Open `http://localhost:8000`.
3. Confirm the page loads without browser console errors.
4. Confirm the fake instance list appears.
5. Click an instance and confirm the details page loads.

Expected result: the UI works before AWS, AI, or Terraform is connected.

## 6. Stage 2 — Connect read-only EC2 discovery

### Build second

1. Add settings for AWS region and environment.
2. Implement an `EC2Client` interface.
3. Implement a boto3-backed EC2 adapter.
4. Retrieve instance ID, instance type, state, region, launch time, tags, and basic configuration.
5. Handle pagination and clear AWS errors.
6. Keep the fake adapter for offline development.
7. Replace fake dashboard data with the adapter result when AWS mode is enabled.

### Required AWS access

The first role is read-only and should cover only the initial workflow:

- `ec2:DescribeInstances`
- `ec2:DescribeTags` when needed
- `sts:GetCallerIdentity` for account verification

No Terraform apply permission is added at this stage.

### Test

Unit tests mock `describe_instances`, verify pagination, verify tags and states are normalized, and verify AWS errors become safe application errors.

Manual AWS check:

```bash
aws sts get-caller-identity
aws ec2 describe-instances --region "$AWS_REGION"
```

Run the application and confirm real instances appear in the UI. If credentials are absent, the app must show a useful error and must not crash or expose secrets.

## 7. Stage 3 — Connect CloudWatch metrics

### Build third

1. Define a `MetricSummary` model.
2. Implement a `CloudWatchClient` interface.
3. Implement a boto3-backed CloudWatch adapter.
4. Start with `CPUUtilization`, `NetworkIn`, `NetworkOut`, and `StatusCheckFailed`.
5. Support a configured 7-day window first.
6. Add 30-day history after the 7-day path works.
7. Calculate average, P95 where enough samples exist, maximum, sample count, and missing-data status.
8. Display metric cards and a small table in the instance page.

### Test

Use fixed CloudWatch fixtures to verify time-window construction, aggregation, P95 and maximum behavior, empty or partial metric results, status-check failures, and that missing metrics are not converted to zero.

Manual check: compare UI values with the AWS console for the same period, confirm timestamps are visible, and confirm unavailable metrics are labelled unavailable.

## 8. Stage 4 — Add deterministic analysis before AI

### Build fourth

1. Add configurable thresholds for CPU average, CPU P95, and CPU maximum.
2. Add a deterministic candidate evaluator.
3. Mark an instance as a possible rightsizing candidate only when it is running, enough history exists, average CPU is below threshold, P95 and maximum are below safety thresholds, and no recent status-check failure is present.
4. Return `candidate`, `not_candidate`, or `needs_more_data`.
5. Include facts and thresholds that produced the decision.
6. Do not select a final instance type using only the LLM.

### Test scenarios

Create fixtures for healthy low utilization, high average utilization, low average with high spikes, failed status checks, insufficient samples, missing metrics, and stopped instances.

Expected result: deterministic tests decide whether AI analysis is appropriate.

## 9. Stage 5 — Add optional cost and savings data

Add this after EC2 metrics work. It is needed for credible savings suggestions but remains separate from the first AWS connection.

### Build fifth

1. Add a Cost Explorer adapter behind an interface.
2. Retrieve account/service/time-window cost data available to the account.
3. Record currency, period, source, and attribution quality.
4. Label service-level or approximate attribution clearly.
5. Add a deterministic savings service.
6. Keep the LLM out of the arithmetic.

### Test

Test current minus proposed cost using fixed pricing fixtures, zero/negative/missing cost, currency and period handling, and reproducibility of monthly and annual savings. Compare a sample total with Cost Explorer manually and document resource-level attribution limitations.

## 10. Stage 6 — Add the single runtime AI provider

### Build sixth

1. Define an `LLMProvider` interface.
2. Implement one provider adapter selected by configuration.
3. Do not implement multiple runtime providers or agents.
4. Build `OptimizationContext` from resource identity, configuration, metric summaries, timestamps, health, cost/savings when available, candidate facts, and missing evidence.
5. Mark tags and collected text as untrusted data.
6. Define a structured recommendation schema.
7. Validate the response with Pydantic.
8. Reject invalid IDs, unsupported changes, missing fields, and inconsistent values.
9. Store provider/model metadata without storing secrets.

### AI responsibilities

- Explain the evidence.
- Describe why the resource may be overprovisioned.
- Identify concerns and missing evidence.
- Suggest a possible configuration change.
- Provide qualitative risk and confidence.

### AI must not do

- Calculate authoritative savings.
- Call AWS.
- Run Terraform or shell commands.
- Override deterministic candidate or policy decisions.
- Receive credentials.

### Test

Mock valid recommendations, `reject`, `needs_more_data`, malformed JSON, invalid enums, wrong resource IDs, unsupported types, prompt-injection-like tag text, provider timeout, and rate-limit responses.

Expected result: only schema-valid, evidence-grounded recommendations reach the UI.

## 11. Stage 7 — Connect recommendation UI

### Build seventh

1. Add an `Analyze` button to the instance page.
2. Add a backend analysis endpoint.
3. Add an in-progress state using HTMX.
4. Show current/proposed configuration, metric evidence, timestamps, reasoning, concerns, risk, confidence, validation requirements, and deterministic savings.
5. Add `Approve recommendation` and `Reject recommendation` buttons.
6. Record approval decision, user, timestamp, and recommendation version.

### Test

Verify that analysis requires a valid resource, provider failure produces a safe error state, approval changes only workflow state, rejection cannot create Terraform changes, and duplicate requests do not create uncontrolled duplicates.

Manual check: analyze a fixture instance and confirm the page is understandable to an engineer without reading logs.

## 12. Stage 8 — Generate Terraform change/diff

### Build eighth

1. Add Terraform mapping input for a known example resource.
2. Start with a simple explicit Terraform variable or resource block.
3. Generate a proposed diff without automatically editing production files.
4. Display old and new values in the UI.
5. Add Terraform formatting and validation in a controlled working directory.
6. Add a plan command only after diff generation is reliable.
7. Parse plan JSON and summarize add/change/destroy counts.
8. Block ambiguous mapping, detected drift, and unrelated resource impact.

### Initial Terraform safety boundary

The first Terraform feature produces a reviewable change/diff only. It does not run `terraform apply`.

### Test

Verify known mapping success, ambiguous mapping failure, exact intended diff, successful `terraform fmt` and `terraform validate`, and blocking of unexpected destroys or unrelated changes.

Manual check: approve a recommendation, open the generated diff, confirm it matches the UI, and confirm no apply occurs.

## 13. Stage 9 — Approval and controlled plan review

### Build ninth

1. Keep recommendation approval separate from Terraform plan approval.
2. Require both approvals before any future apply capability.
3. Add immutable-ish audit events for state changes.
4. Add deterministic plan safety policy.
5. Keep apply disabled by default with a feature flag.

### Test

Verify that no approval means no plan execution, recommendation approval alone does not authorize apply, failed validation cannot receive plan approval, audit events contain actor/timestamp/resource/decision/evidence, and policy failure prevents progression.

## 14. Stage 10 — Optional controlled apply

Begin only after the previous workflow is reliable in a disposable environment.

1. Add a separate Terraform execution role.
2. Use an approved saved plan rather than an unreviewed fresh plan.
3. Require recommendation approval and plan approval.
4. Add an explicit apply action with a clear confirmation screen.
5. Capture a pre-change baseline.
6. Execute only the intended plan.
7. Record command result and audit data.

Test only with disposable infrastructure: provision one EC2 resource, run analysis, approve the recommendation, inspect the plan, approve the plan, apply the saved plan, verify health, and destroy the test environment. Production apply remains disabled until security, rollback, authorization, and verification requirements are complete.

## 15. Stage 11 — Post-change verification

Later, store pre-change metrics and cost baseline, collect after-change CPU/health/latency/errors/cost, compare windows, classify successful/inconclusive/failed, record realized savings, and define approval-controlled rollback using the previous known-good Terraform configuration or plan.

Test healthy change, degraded health, missing after-change data, and rollback-policy behavior.

## 16. Complete test strategy

### Unit tests

Test metric aggregation, thresholds, candidate detection, cost arithmetic, context construction, schema validation, Terraform diff generation, and plan policy without external services.

### API tests

Use FastAPI's test client for health, instance listing, instance details, analysis, approval, rejection, and Terraform diff routes.

### Adapter tests

Mock boto3 and the LLM provider. Verify request construction, response normalization, pagination, retries, timeouts, and safe errors.

### Evaluation tests

Use known scenarios: oversized EC2, normal EC2, undersized EC2, high spike, missing memory, failed health check, production tag, prompt-injection-like tag, no cost data, and unexpected Terraform destroy.

### Manual smoke test

```text
Start app
  -> open dashboard
  -> list EC2 instances
  -> open one instance
  -> view CloudWatch metrics
  -> run deterministic analysis
  -> request AI recommendation
  -> review evidence and concerns
  -> approve recommendation
  -> review Terraform diff
  -> confirm no apply occurred
```

### Quality commands

```bash
ruff check .
pytest
uvicorn app.main:app --reload --port 8000
```

When Terraform is introduced:

```bash
terraform fmt -check -recursive
terraform validate
terraform plan
```

## 17. Definition of done for the first MVP

The MVP is complete only when the app starts locally, the UI lists real EC2 instances using read-only access, one details page shows real CloudWatch metrics, missing data and AWS errors are safe and visible, deterministic checks run before AI, one configured LLM produces validated structured output, the UI shows evidence/reasoning/concerns/risk/savings, a human can approve or reject, an approved recommendation produces a reviewable Terraform diff, unsafe plans are blocked, no infrastructure is automatically applied, and unit/API/adapter/evaluation tests pass.

## 18. Expansion after the first MVP

Only after this workflow works should we add PostgreSQL, Cost Explorer history, authentication, React, background workers, scheduling, Terraform apply, verification, more AWS services, multi-account support, RBAC, observability, and controlled automation.
