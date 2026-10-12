from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.analysis.candidate import evaluate as evaluate_candidate
from app.aws.cloudwatch import (
    BotoCloudWatchAdapter,
    CloudWatchClient,
    FakeCloudWatchAdapter,
)
from app.aws.ec2 import BotoEC2Adapter, EC2Client, FakeEC2Adapter
from app.config import settings

app = FastAPI(title="CloudSage", version="0.3.0")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


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
        context={**_base_context(), "instances": [i.model_dump() for i in instances]},
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
        context={**_base_context(), "instances": [i.model_dump() for i in instances]},
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
        )

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
        },
    )
