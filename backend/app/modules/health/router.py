from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


@router.get("/health", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Public process liveness only (API_DESIGN Group 20). No DB or auth dependency."""
    return LivenessResponse(status="alive")
