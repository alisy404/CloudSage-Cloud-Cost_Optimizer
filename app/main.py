from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="CloudSage", version="0.1.0")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)

FAKE_INSTANCES = [
    {
        "id": "i-0123456789abcdef0",
        "name": "api-server",
        "type": "t3.large",
        "state": "running",
        "region": "ap-south-1",
    },
    {
        "id": "i-0fedcba9876543210",
        "name": "worker-server",
        "type": "t3.medium",
        "state": "stopped",
        "region": "ap-south-1",
    },
]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"instances": FAKE_INSTANCES},
    )


@app.get("/instances", response_class=HTMLResponse)
def instance_list(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="partials/instance_list.html",
        context={"instances": FAKE_INSTANCES},
    )


@app.get("/instances/{instance_id}", response_class=HTMLResponse)
def instance_detail(request: Request, instance_id: str) -> HTMLResponse:
    instance = next(
        (item for item in FAKE_INSTANCES if item["id"] == instance_id),
        None,
    )
    if instance is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    return templates.TemplateResponse(
        request=request,
        name="instance.html",
        context={"instance": instance},
    )
