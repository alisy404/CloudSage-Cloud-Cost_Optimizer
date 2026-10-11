# CloudSage Engineering and Safety Rules

## Runtime AI

1. Multiple AI assistants may help during development.
2. The deployed product uses exactly one LLM provider/API key at runtime.
3. Do not build a multi-agent runtime for the initial product.
4. Keep a provider adapter so the one runtime provider can be replaced without rewriting business logic.
5. Send only bounded, relevant, timestamped evidence to the model.
6. Mark logs, tags, commit messages, and collected strings as untrusted data.
7. Never send AWS credentials, LLM keys, database passwords, or secrets to the model.
8. Require structured output and reject malformed responses.
9. Treat model confidence as a signal, never as proof.

## Infrastructure

1. Start with EC2 and rightsizing/underutilization only.
2. Do not add services until the EC2 lifecycle is stable.
3. Initial AWS access is read-only for discovery, metrics, costs, and identity verification.
4. The AI never receives unrestricted AWS write access.
5. Terraform is the preferred infrastructure change mechanism.
6. Terraform mapping must be deterministic enough before a change is generated.
7. Detect drift before generating a change.
8. Run format, validate, plan, and JSON plan analysis before apply.
9. Block unexpected destroys, unrelated changes, and policy violations.
10. Require human approval before recommendation execution and before apply.
11. Use a separate execution role for Terraform writes.
12. Capture a baseline and verify health and savings after every applied optimization.
13. Rollback is controlled by approval/policy unless an explicitly documented emergency policy exists.

## Data and financials

1. Deterministic backend code performs all financial arithmetic.
2. Store pricing source, timestamp, currency, period, and assumptions.
3. Mark shared or service-level cost attribution as approximate.
4. Never treat missing metrics as zero.
5. Include average plus P95/P99/max where relevant.
6. Include freshness timestamps on cost and metric evidence.
7. CPU alone cannot justify rightsizing when memory or workload evidence is important.
8. Record estimated versus realized savings.

## Security

1. Use least-privilege IAM and short-lived roles where possible.
2. Do not commit credentials, `.env` secrets, Terraform secrets, or generated sensitive state.
3. Protect Terraform state and use remote state with locking for shared environments.
4. Validate API inputs and authorize approval operations.
5. Add authentication, authorization, CSRF protection where browser sessions are used, and rate limiting where exposed.
6. Scan dependencies and container images.
7. Do not allow arbitrary shell commands from model output.
8. Do not apply when evidence is incomplete, AI output is invalid, policy fails, approval is absent, or provider analysis is unavailable.

## Engineering

1. Keep service implementations behind plugin interfaces.
2. Keep deterministic logic unit-testable without AWS, PostgreSQL, Terraform, or the LLM.
3. Use fixtures for known infrastructure scenarios.
4. Preserve idempotency for scans and state transitions where practical.
5. Use structured errors and logs without secrets.
6. Pin versions when moving toward deployment.
7. A feature is not done until it has tests, documentation, security review, repeatable setup, and rollback/failure behavior.
8. Do not introduce a new AWS service, AI architecture, deployment platform, and automation model in one version without an explicit decision.

## Operations

Monitor API latency, worker failures, AWS errors/throttling, database health, LLM latency/errors, token usage, recommendation throughput, approval latency, Terraform failures, and verification failures.

Monitor optimization quality through acceptance/rejection rate, false positives, predicted versus realized savings, failed optimizations, rollback frequency, average savings, and time from detection to verification.
