# CloudSage monitoring test mode

The current test configuration is intentionally based on the latest 60 minutes so a newly created EC2 instance can be exercised without waiting days:

```dotenv
CLOUDWATCH_WINDOW_MINUTES=60
CLOUDWATCH_PERIOD_SECONDS=300
ANALYSIS_ALLOW_SHORT_WINDOW=true
```

CloudWatch EC2 metrics are requested in five-minute periods. The deterministic analyzer may use the available short history and uses the maximum as a temporary P95 proxy when a statistical P95 is not yet possible. This is for validation only; it is not sufficient evidence for a production rightsizing decision.

## Switch to completed-project monitoring

In the deployment `.env`, change the settings to:

```dotenv
# Disable minute mode and select the intended historical window.
CLOUDWATCH_WINDOW_MINUTES=0
CLOUDWATCH_WINDOW_DAYS=7
CLOUDWATCH_PERIOD_SECONDS=3600
ANALYSIS_ALLOW_SHORT_WINDOW=false
```

For a more conservative completed product, use `CLOUDWATCH_WINDOW_DAYS=30` after the 7-day path has been verified. Keep the five-minute period if finer-grained history is required and the CloudWatch request/cost limits are acceptable; otherwise the original one-hour period is appropriate for the 7-day/30-day summary.

After changing settings, restart Uvicorn. Confirm the instance page says `7-day window` (or `30-day window`), the metric timestamps cover the intended period, and newly launched instances correctly show `needs_more_data` rather than being treated as zero-utilization.

## Safety settings that remain unchanged

- `AWS_MODE=true` uses read-only EC2 and CloudWatch adapters.
- `TERRAFORM_APPLY_ENABLED=false` remains disabled.
- The LLM never receives AWS credentials and cannot execute AWS, shell, or Terraform actions.
- Short-window mode must not be used as the basis for a real production change.
