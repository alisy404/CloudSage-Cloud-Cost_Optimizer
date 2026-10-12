from datetime import datetime

from pydantic import BaseModel


class EC2Instance(BaseModel):
    """Normalised representation of a single EC2 instance."""

    id: str
    name: str
    type: str
    state: str  # running | stopped | terminated | pending | …
    region: str
    launch_time: datetime | None = None
    tags: dict[str, str] = {}
