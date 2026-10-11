# CloudSage Project Requirements

## Product definition

> CloudSage is an AI-powered AWS infrastructure cost optimization platform. It combines AWS resource configuration, cost, utilization, health, operational context, and Terraform information to identify waste and produce safe, explainable infrastructure recommendations.

> It is an infrastructure intelligence layer, not a Cost Explorer clone and not a generic chatbot connected directly to AWS.

**Core lifecycle:** `DISCOVER -> MEASURE -> DETECT -> REASON -> RECOMMEND -> APPROVE -> PLAN -> APPLY -> VERIFY -> AUDIT`

## Problem

AWS billing, CloudWatch metrics, infrastructure configuration, Terraform code, alerts, and operational history are fragmented. Engineers must manually correlate them to answer what exists, what it costs, how it is used, whether its configuration is still appropriate, what should change, what could go wrong, how to change it through IaC, and whether the change worked.

CloudSage automates that evidence-gathering and decision-support workflow while keeping infrastructure writes behind deterministic policy and human approval.

## Non-negotiable principles

1. AI recommends; deterministic systems verify.
2. Financial calculations are performed by backend code, never trusted to the LLM.
3. The deployed product uses exactly one selected LLM provider/API key.
4. Multiple AI tools are allowed during development only and are not runtime dependencies.
5. The LLM never receives AWS credentials or unrestricted shell/AWS access.
6. Terraform is the preferred infrastructure change mechanism.
7. Production and destructive changes require explicit approval.
8. Incomplete evidence, invalid AI output, unexpected plans, or failed policy checks cause a fail-closed result.
9. Every recommendation and state-changing action is auditable.
10. Each project version must work before the next layer is added.

## Initial scope

The first implementation supports one AWS resource family: EC2 instances. The first optimization is rightsizing/underutilization detection.

The first read-only milestone must discover EC2 metadata, collect CloudWatch utilization and health metrics, retrieve Cost Explorer data, normalize observations, run deterministic candidate rules, build bounded AI context, call one runtime LLM provider, validate structured output, calculate savings independently, and store/expose the recommendation without changing infrastructure.

## Later scope

After EC2 is stable, add EBS, Elastic IP, S3, RDS, ALB, ECS, Lambda, Auto Scaling, NAT Gateway, data transfer, and dependency-aware recommendations as separate service plugins. Later add Terraform mapping/plan analysis, approvals, controlled apply, verification, multi-account support, RBAC, workers, scheduling, notifications, observability, historical outcomes, RAG, what-if simulation, and carefully controlled low-risk automation.

## Inputs

### AWS and infrastructure

- Account, region, resource ID, service, resource type, state, launch time, tags
- Current configuration and dependencies
- EC2 instance type and relevant metadata
- Terraform state, configuration, modules, variables, outputs, and plan JSON when available

### Cost

- Daily and monthly cost observations
- Service and tag dimensions
- Cost trends, currency, pricing source, and data freshness
- Resource-level attribution where AWS supports it; otherwise an explicit approximate flag

### Utilization and health

- CPU average, P95/P99, and maximum
- Memory where available
- Network, disk, request, latency, error, throughput, and health metrics where applicable
- Status-check failures, alerts, incidents, and operational history

### Context

- Environment, criticality, owner, application identity, SLA/SLO information
- Historical recommendations and outcomes

## Required output

Each recommendation includes resource identity, optimization type, decision, current and proposed configuration, timestamped evidence, deterministic current/proposed/monthly/annual costs, risk, model confidence as an explanatory signal, concerns, missing evidence, required validation, Terraform mapping/plan impact when available, workflow status, and audit history.

Example:

```json
{
  "resource_id": "i-123456",
  "service": "ec2",
  "optimization_type": "rightsizing",
  "decision": "recommend",
  "current_configuration": {"instance_type": "t3.large"},
  "recommended_configuration": {"instance_type": "t3.small"},
  "estimated_monthly_savings": 38.16,
  "estimated_annual_savings": 457.92,
  "risk": "low",
  "confidence": 0.91,
  "reasoning": ["Sustained utilization is low"],
  "concerns": ["Memory data is unavailable"],
  "required_validation": ["Validate memory before applying"],
  "status": "awaiting_approval"
}
```

## Functional requirements

- Use least-privilege AWS APIs with pagination, retries, backoff, throttling handling, and freshness metadata.
- Join resource, cost, metrics, health, Terraform, and history data.
- Detect candidates before invoking AI and provide bounded context rather than arbitrary raw AWS data.
- Reject malformed or unsupported AI output and cross-check IDs, current values, proposed values, and savings.
- Separate analysis, approval, plan, apply, verification, and audit state transitions.
- Generate controlled Terraform changes only after reliable mapping.
- Run `terraform fmt`, `terraform validate`, and `terraform plan`.
- Block unexpected destroys, unrelated changes, drift, or policy violations.
- Verify health and realized savings after approved changes.

## Non-functional requirements

- Secure by default and fail closed for writes.
- Structured errors and logs without secrets.
- Idempotent scans where practical and paginated APIs.
- Explicit timestamps, source labels, and uncertainty.
- Provider abstraction without runtime multi-model complexity.
- Testable deterministic logic independent of AWS and the LLM.
- Repeatable local setup using Docker and environment configuration.

## Success criteria

The first accepted end-to-end slice discovers one EC2 instance, collects cost and utilization, detects a deterministic candidate, obtains a structured recommendation from one runtime LLM, calculates savings independently, validates and stores the recommendation, and returns it through the API without changing infrastructure.
