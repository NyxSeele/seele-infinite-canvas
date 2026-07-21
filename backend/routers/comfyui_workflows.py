"""GET /api/comfyui/workflows — list registered ComfyUI workflow templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from comfyui.workflow_registry import list_workflows
from core.dependencies import get_current_user
from models import User

router = APIRouter(tags=["comfyui"])


@router.get("/api/comfyui/workflows")
async def get_comfyui_workflows(user: User = Depends(get_current_user)):
    workflows = list_workflows()
    return {
        "workflows": [
            {
                "key": item["key"],
                "source": item["source"],
                "capability": item["capability"],
            }
            for item in workflows
        ]
    }
