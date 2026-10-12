from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.aws.ec2 import BotoEC2Adapter, EC2Client, FakeEC2Adapter
from app.config import settings

app = FastAPI(title="CloudSage", version="0.2.0")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


def _get_ec2_client() -> EC2Client:
    """Return the real boto3 adapter when AWS_MODE=true, otherwise the fake."""
    if settings.aws_mode:
        return BotoEC2Adapter(region=settings.aws_region)
    return FakeEC2Adapter()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _base_context() -> dict:
    """Common template context injected into every page."""
    return {
        "settings_aws_mode": settings.aws_mode,
        "settings_region": settings.aws_region,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    client = _get_ec2_client()
    try:
        instances = client.list_instances()
    except RuntimeError as exc:
        # Show a safe error page rather than crashing or exposing AWS details.
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
    client = _get_ec2_client()
    try:
        instance = client.get_instance(instance_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    return templates.TemplateResponse(
        request=request,
        name="instance.html",
        context={"instance": instance.model_dump()},
    )
