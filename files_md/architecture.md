# CloudSage Architecture

## Architectural goal

> CloudSage connects AWS evidence to controlled infrastructure decisions. Data collection, deterministic analysis, AI reasoning, policy, Terraform execution, and verification are separate so no model response can directly change infrastructure.

## Logical architecture

```text
User / UI
  -> API / Orchestrator
  -> Context Builder <- PostgreSQL <- normalized observations
  -> Optimization Engine <- AWS collectors <- EC2 / CloudWatch / Cost Explorer
  -> AI Reasoner <- one runtime LLM provider
  -> Output Validator
  -> Risk and Policy Engine
  -> Recommendation + Human Approval
  -> Terraform Intelligence -> fmt -> validate -> plan -> plan analysis
  -> Second approval
  -> Controlled Terraform Apply -> AWS
  -> Post-change Verification -> PostgreSQL / Audit
```

## Runtime components

### API and orchestration

FastAPI exposes health, resource, scan, analysis, recommendation, approval, Terraform, verification, and audit endpoints. The orchestrator starts jobs and enforces workflow state transitions.

### AWS collectors

Provider-specific boto3 collectors return normalized domain objects. The first collector is EC2. Future service plugins cover EBS, EIP, S3, RDS, ALB, ECS, Lambda, and network resources.

### Cost and metrics collectors

Cost Explorer retrieves supported account/service/time-window data with currency, period, dimensions, source, and freshness. CloudWatch aggregates 7-day and 30-day windows with average, P95/P99, maximum, sample count, missing-data markers, and timestamps.

### Normalization and persistence

Raw provider responses become stable internal contracts before candidate detection. PostgreSQL stores resources, metrics, costs, Terraform mappings, candidates, recommendations, plans, approvals, verification results, and audit events.

### Optimization engine

This layer is deterministic. It evaluates thresholds, data sufficiency, health, recent incidents, configuration, and known constraints. It produces candidates such as `possible_rightsizing`; it does not use the LLM for arithmetic.

### Context builder and AI reasoner

The context builder creates a bounded package with relevant evidence, timestamps, source labels, uncertainty, and untrusted-text markers. Secrets, credentials, arbitrary commands, and irrelevant data are excluded. One provider-neutral adapter is enabled at runtime; the model interprets evidence and returns structured output but cannot execute AWS or Terraform actions.

### Validator and policy engine

The validator checks schema, allowed enums, resource identity, current configuration, proposed values, evidence references, and numeric fields. The policy engine independently evaluates environment, criticality, action type, impact, drift, approvals, and plan contents.

### Terraform intelligence and execution

Terraform state, IDs, tags, module outputs, and deterministic metadata map an AWS resource to code. A change is generated only when mapping is reliable. Formatting, validation, plan generation, JSON parsing, allowed-impact checks, approval, and apply are separate states.

### Verification

Before apply, CloudSage stores a baseline. After the change it measures health, utilization, performance, and cost, classifies the result as successful, inconclusive, or failed, and follows the configured rollback policy.

## Data flow

1. Discover AWS resources and normalize identities.
2. Collect cost, utilization, health, and operational data.
3. Join evidence for the selected resource and period.
4. Run deterministic candidate rules.
5. Build bounded AI context.
6. Call the single configured LLM provider.
7. Validate output against schemas and deterministic facts.
8. Calculate savings independently.
9. Apply risk and approval policy.
10. Persist recommendation and audit event.
11. Map the resource to Terraform when supported.
12. Generate and inspect a Terraform plan.
13. Require approval before apply.
14. Verify the post-change baseline and record realized savings.

## Security boundary

```text
LLM (no AWS credentials)
        |
CloudSage API and orchestrator
        |
Deterministic validator and policy engine
        |
Separate AWS/Terraform execution role
        |
AWS target resources
```

The initial IAM role is read-only for EC2, CloudWatch, Cost Explorer, and STS identity checks. The later Terraform execution role is separate. No model receives administrator credentials or arbitrary command execution.

## Deployment evolution

### MVP

One FastAPI process, PostgreSQL in Docker, a local Terraform working directory, and synchronous or simple background scans.

### Growth

Move long-running scans to worker processes with Redis or a queue, then add scheduling, observability, notifications, and a web UI.

### Production

Use K3s only when workload and operational needs justify it. Add protected PostgreSQL, secret management, RBAC, remote Terraform state with locking, backups, monitoring, and account isolation.

## Plugin architecture

```text
OptimizerPlugin
  discover()
  collect_metrics()
  calculate_cost()
  find_candidates()
  build_context()
  generate_change()
  verify()

EC2Optimizer, EBSOptimizer, EIPOptimizer, S3Optimizer,
RDSOptimizer, ALBOptimizer, ECSOptimizer, LambdaOptimizer,
NATGatewayOptimizer
```

The core workflow depends on this interface rather than spreading service-specific conditionals through the application.

## Reliability

Collectors support pagination, retries with backoff, throttling, caching, partial data, and freshness metadata. Jobs use idempotency keys and observable status. The system fails closed when evidence is incomplete, the LLM is unavailable, policy evaluation fails, or a Terraform plan contains unexpected impact.
