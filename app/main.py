from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.ai.provider import (
    FakeLLMProvider,
    LLMProvider,
    LLMProviderError,
    OpenAICompatibleProvider,
)
from app.ai.service import analyze_optimization
from app.analysis.candidate import evaluate as evaluate_candidate
from app.analysis.savings import calculate_savings
from app.aws.cloudwatch import (
    BotoCloudWatchAdapter,
    CloudWatchClient,
    FakeCloudWatchAdapter,
)
from app.aws.ec2 import BotoEC2Adapter, EC2Client, FakeEC2Adapter
from app.aws.pricing import get_instance_pricing
from app.config import settings
from app.terraform.diff import TerraformDiffError, generate_instance_type_diff
from app.terraform.workflow import (
    PlanSummary,
    TerraformWorkflowError,
    require_apply_enabled,
    validate_plan,
)

app = FastAPI(title="CloudSage", version="0.3.0")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)

# Stage 7 local workflow store. This is intentionally in-memory until the
# persistence stage; one current recommendation is retained per EC2 instance.
_recommendations: dict[str, dict] = {}
_plans: dict[str, dict] = {}

# Explicit mapping only. Stage 8 does not infer Terraform ownership from tags.
_terraform_mappings = {
    "i-0123456789abcdef0": "aws_instance.api_server",
}


# ---------------------------------------------------------------------------
# Adapter factories
# ---------------------------------------------------------------------------


def _get_ec2_client() -> EC2Client:
    """Return the real boto3 adapter when AWS_MODE=true, otherwise the fake."""
    if settings.aws_mode:
        return BotoEC2Adapter(region=settings.aws_region)
    return FakeEC2Adapter()


def _get_cloudwatch_client() -> CloudWatchClient:
    """Return the real CloudWatch adapter when AWS_MODE=true, otherwise fake."""
    if settings.aws_mode:
        return BotoCloudWatchAdapter(region=settings.aws_region)
    return FakeCloudWatchAdapter()


def _get_llm_provider() -> LLMProvider:
    """Use the configured single provider, or the offline provider locally."""
    if settings.llm_provider and settings.llm_provider.lower() != "fake":
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )
    return FakeLLMProvider()


# ---------------------------------------------------------------------------
# Shared template context
# ---------------------------------------------------------------------------


def _base_context() -> dict:
    """Common template context injected into every page."""
    return {
        "settings_aws_mode": settings.aws_mode,
        "settings_region": settings.aws_region,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _enrich_instances_with_pricing(instances: list) -> list[dict]:
    enriched = []
    for inst in instances:
        d = inst.model_dump()
        pricing = get_instance_pricing(inst.type, region=inst.region)
        d["monthly_cost"] = f"${pricing.monthly_rate_usd:.2f}" if pricing else "—"
        d["hourly_cost"] = f"${pricing.hourly_rate_usd:.4f}" if pricing else "—"
        enriched.append(d)
    return enriched


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    client = _get_ec2_client()
    try:
        instances = client.list_instances()
    except RuntimeError as exc:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={**_base_context(), "instances": [], "error": str(exc)},
        )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={**_base_context(), "instances": _enrich_instances_with_pricing(instances)},
    )


@app.get("/instances", response_class=HTMLResponse)
def instance_list(request: Request) -> HTMLResponse:
    client = _get_ec2_client()
    try:
        instances = client.list_instances()
    except RuntimeError as exc:
        return templates.TemplateResponse(
            request=request,
            name="partials/instance_list.html",
            context={**_base_context(), "instances": [], "error": str(exc)},
        )
    return templates.TemplateResponse(
        request=request,
        name="partials/instance_list.html",
        context={**_base_context(), "instances": _enrich_instances_with_pricing(instances)},
    )


@app.get("/instances/{instance_id}", response_class=HTMLResponse)
def instance_detail(request: Request, instance_id: str) -> HTMLResponse:
    ec2 = _get_ec2_client()
    cw = _get_cloudwatch_client()

    # Fetch instance — 404 if not found, 502 on AWS error.
    try:
        instance = ec2.get_instance(instance_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    # Fetch metrics — surface error in UI rather than crashing the page.
    metrics = None
    metrics_error: str | None = None
    try:
        metrics = cw.get_instance_metrics(
            instance_id=instance_id,
            window_days=settings.cloudwatch_window_days,
        )
    except RuntimeError as exc:
        metrics_error = str(exc)

    # Deterministic candidate evaluation (Stage 4).
    candidate_result = None
    if metrics is not None:
        candidate_result = evaluate_candidate(
            instance=instance,
            metrics=metrics,
            cpu_avg_threshold=settings.analysis_cpu_avg_threshold,
            cpu_p95_threshold=settings.analysis_cpu_p95_threshold,
            cpu_max_threshold=settings.analysis_cpu_max_threshold,
            allow_short_window=settings.analysis_allow_short_window,
        )

    # Deterministic savings and cost calculations (Stage 5).
    savings = calculate_savings(instance=instance, candidate_result=candidate_result)

    return templates.TemplateResponse(
        request=request,
        name="instance.html",
        context={
            **_base_context(),
            "instance": instance.model_dump(),
            "metrics": metrics.model_dump() if metrics else None,
            "metrics_error": metrics_error,
            "window_days": settings.cloudwatch_window_days,
            "candidate_result": candidate_result.model_dump() if candidate_result else None,
            "savings": savings.model_dump(),
        },
    )


@app.post("/instances/{instance_id}/analyze", response_class=HTMLResponse)
def analyze_instance(request: Request, instance_id: str) -> HTMLResponse:
    """Run Stage 6 AI analysis and return the recommendation UI partial."""
    ec2 = _get_ec2_client()
    cw = _get_cloudwatch_client()

    try:
        instance = ec2.get_instance(instance_id)
    except RuntimeError as exc:
        return templates.TemplateResponse(
            request=request,
            name="partials/recommendation.html",
            context={"analysis_error": str(exc)},
        )
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        metrics = cw.get_instance_metrics(
            instance_id=instance_id,
            window_days=settings.cloudwatch_window_days,
        )
    except RuntimeError as exc:
        return templates.TemplateResponse(
            request=request,
            name="partials/recommendation.html",
            context={"analysis_error": str(exc)},
        )

    candidate = evaluate_candidate(
        instance=instance,
        metrics=metrics,
        cpu_avg_threshold=settings.analysis_cpu_avg_threshold,
        cpu_p95_threshold=settings.analysis_cpu_p95_threshold,
        cpu_max_threshold=settings.analysis_cpu_max_threshold,
        allow_short_window=settings.analysis_allow_short_window,
    )
    savings = calculate_savings(instance=instance, candidate_result=candidate)

    provider_error: str | None = None
    provider_name = _get_llm_provider().provider_name
    try:
        _, recommendation = analyze_optimization(
            instance=instance,
            metrics=metrics,
            candidate=candidate,
            savings=savings,
            provider=_get_llm_provider(),
        )
    except LLMProviderError as exc:
        # Keep the real AWS evidence useful when the external model is
        # temporarily unavailable. This fallback does not call AWS or make
        # changes; it produces a clearly labelled deterministic recommendation.
        provider_error = str(exc)
        _, recommendation = analyze_optimization(
            instance=instance,
            metrics=metrics,
            candidate=candidate,
            savings=savings,
            provider=FakeLLMProvider(),
        )
        provider_name = "deterministic fallback"
    except (ValueError, RuntimeError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="partials/recommendation.html",
            context={
                "analysis_error": str(exc),
                "candidate_result": candidate.model_dump(),
            },
        )

    recommendation_record = _recommendations.get(instance_id)
    if recommendation_record and recommendation_record["version"] == recommendation.model_dump_json():
        recommendation_id = recommendation_record["id"]
        workflow_status = recommendation_record["status"]
        created_at = recommendation_record["created_at"]
    else:
        recommendation_id = f"rec-{instance_id}"
        workflow_status = "pending"
        created_at = datetime.now(UTC).isoformat()
        _recommendations[instance_id] = {
            "id": recommendation_id,
            "instance_id": instance_id,
            "recommendation": recommendation.model_dump(),
            "version": recommendation.model_dump_json(),
            "status": workflow_status,
            "actor": None,
            "decided_at": None,
            "created_at": created_at,
        }

    return templates.TemplateResponse(
        request=request,
        name="partials/recommendation.html",
        context={
            "recommendation": recommendation.model_dump(),
            "instance_id": instance_id,
            "provider_name": provider_name,
            "provider_error": provider_error,
            "recommendation_id": recommendation_id,
            "workflow_status": workflow_status,
            "workflow_actor": recommendation_record["actor"] if recommendation_record else None,
            "workflow_decided_at": recommendation_record["decided_at"] if recommendation_record else None,
        },
    )


def _update_recommendation(request: Request, instance_id: str, status: str) -> HTMLResponse:
    record = _recommendations.get(instance_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Recommendation not found; analyze the instance first")
    if record["status"] != "pending":
        return templates.TemplateResponse(
            request=request,
            name="partials/recommendation.html",
            context={
                "recommendation": record["recommendation"],
                "provider_name": "stored recommendation",
                "recommendation_id": record["id"],
                "workflow_status": record["status"],
                "workflow_actor": record["actor"],
                "workflow_decided_at": record["decided_at"],
                "instance_id": instance_id,
            },
        )

    actor = request.headers.get("X-User", "local-user")
    record["status"] = status
    record["actor"] = actor
    record["decided_at"] = datetime.now(UTC).isoformat()
    return templates.TemplateResponse(
        request=request,
        name="partials/recommendation.html",
        context={
            "recommendation": record["recommendation"],
            "provider_name": "stored recommendation",
            "recommendation_id": record["id"],
            "workflow_status": record["status"],
            "workflow_actor": record["actor"],
            "workflow_decided_at": record["decided_at"],
            "instance_id": instance_id,
        },
    )


@app.post("/instances/{instance_id}/recommendation/approve", response_class=HTMLResponse)
def approve_recommendation(request: Request, instance_id: str) -> HTMLResponse:
    return _update_recommendation(request, instance_id, "approved")


@app.post("/instances/{instance_id}/recommendation/reject", response_class=HTMLResponse)
def reject_recommendation(request: Request, instance_id: str) -> HTMLResponse:
    return _update_recommendation(request, instance_id, "rejected")


@app.post("/instances/{instance_id}/terraform/diff", response_class=HTMLResponse)
def terraform_diff(request: Request, instance_id: str) -> HTMLResponse:
    """Return a review-only Terraform diff for an approved recommendation."""
    record = _recommendations.get(instance_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Recommendation not found; analyze the instance first")
    try:
        recommendation = record["recommendation"]
        proposed = recommendation.get("recommended_configuration", {}).get("instance_type")
        diff = generate_instance_type_diff(
            instance_id=instance_id,
            current_type=recommendation.get("current_configuration", {}).get("instance_type", ""),
            proposed_type=proposed or "",
            resource_address=_terraform_mappings.get(instance_id),
            approved=record["status"] == "approved",
        )
    except TerraformDiffError as exc:
        return templates.TemplateResponse(
            request=request,
            name="partials/terraform_diff.html",
            context={"terraform_error": str(exc)},
        )
    return templates.TemplateResponse(
        request=request,
        name="partials/terraform_diff.html",
        context={"terraform_diff": diff},
    )


@app.post("/instances/{instance_id}/terraform/plan", response_class=HTMLResponse)
def terraform_plan(request: Request, instance_id: str) -> HTMLResponse:
    record = _recommendations.get(instance_id)
    if not record or record["status"] != "approved":
        return templates.TemplateResponse(
            request=request,
            name="partials/terraform_diff.html",
            context={"terraform_error": "Terraform plan requires recommendation approval"},
        )
    address = _terraform_mappings.get(instance_id)
    try:
        if not address:
            raise TerraformWorkflowError("Terraform mapping is missing or ambiguous")
        summary = PlanSummary(add=0, change=1, destroy=0, resource_addresses=(address,))
        validate_plan(summary, address)
        _plans[instance_id] = {"status": "pending", "actor": None, "summary": summary}
    except TerraformWorkflowError as exc:
        return templates.TemplateResponse(
            request=request,
            name="partials/terraform_diff.html",
            context={"terraform_error": str(exc)},
        )
    return templates.TemplateResponse(
        request=request,
        name="partials/terraform_diff.html",
        context={"terraform_plan": summary, "plan_status": "pending", "plan_instance_id": instance_id},
    )


@app.post("/instances/{instance_id}/terraform/plan/approve", response_class=HTMLResponse)
def approve_terraform_plan(request: Request, instance_id: str) -> HTMLResponse:
    plan = _plans.get(instance_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Terraform plan not found")
    if plan["status"] != "pending":
        return templates.TemplateResponse(request=request, name="partials/terraform_diff.html", context={"terraform_error": "Terraform plan is already decided"})
    plan["status"] = "approved"
    plan["actor"] = request.headers.get("X-User", "local-user")
    return templates.TemplateResponse(request=request, name="partials/terraform_diff.html", context={"terraform_plan": plan["summary"], "plan_status": "approved", "plan_instance_id": instance_id})


@app.post("/instances/{instance_id}/terraform/apply", response_class=HTMLResponse)
def apply_terraform_plan(request: Request, instance_id: str) -> HTMLResponse:
    plan = _plans.get(instance_id)
    try:
        if not plan or plan["status"] != "approved":
            raise TerraformWorkflowError("Terraform apply requires plan approval")
        require_apply_enabled(settings.terraform_apply_enabled)
    except TerraformWorkflowError as exc:
        return templates.TemplateResponse(request=request, name="partials/terraform_diff.html", context={"terraform_error": str(exc)})
    raise HTTPException(status_code=501, detail="Terraform apply executor is not implemented")
