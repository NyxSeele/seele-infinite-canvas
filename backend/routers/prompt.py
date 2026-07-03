from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.dependencies import get_current_user
from model_registry import resolve_generation_profile
from models import User
from schemas.prompt_builder import (
    BuildPromptRequest,
    BuildPromptResponse,
    BuildScriptShotRequest,
    ExpandShotPackageRequest,
    ExpandShotPackageResponse,
    SplitShotBeatsRequest,
    SplitShotBeatsResponse,
    ScriptTableGenerateRequest,
    ScriptTableGenerateResponse,
    ShotLinkingMeta,
)
from services.prompt_builder import (
    build_prompt_from_fields,
    build_script_shot_prompt,
    resolve_style_en_tags,
)
from services.shot_prompt_package import build_shot_prompt_package
from services.split_shot_beats import split_shot_beats
from services.script_shot_strategy import evaluate_visual_reference
from services.prompt_intent import classify_user_intent
from trace_bus import push_trace

router = APIRouter(tags=["prompt"])


class ClassifyIntentRequest(BaseModel):
    text: str = Field(..., min_length=1)
    context: str = Field(default="text", description="text | image | video")
    current_text_mode: str | None = Field(default=None, description="chat | screenplay")


class ClassifyIntentResponse(BaseModel):
    intent: str
    intent_label: str
    confidence: float
    summary: str
    generation_prompt: str
    suggested_text_mode: str | None = None
    warnings: list[str] = Field(default_factory=list)


def _resolve_workflow_type(model_id: str) -> str:
    profile = resolve_generation_profile(model_id=model_id)
    return profile.get("workflow_type") or "sd15"


def _prompt_layers_from_built(built) -> list[str]:
    layers: list[str] = []
    fields = built.parsed_fields or {}
    if fields.get("theme"):
        layers.append("theme")
    positive = built.positive or ""
    if "承接上一镜头" in positive:
        layers.append("prior_shot")
    if fields.get("description"):
        layers.append("shot")
    style = fields.get("style") or ""
    if style and resolve_style_en_tags(style):
        layers.append("style_en")
    return layers


def _to_response(
    built,
    *,
    visual_decision=None,
    narrative_enabled: bool = True,
    trace_id: str | None = None,
) -> BuildPromptResponse:
    use_ref = False
    denoise = None
    note = None
    visual_mode = "none"
    if visual_decision is not None:
        use_ref = visual_decision.use_visual_reference
        denoise = visual_decision.img2img_denoise
        note = visual_decision.note
        visual_mode = visual_decision.visual_mode
    shot_linking = None
    if visual_decision is not None:
        shot_linking = ShotLinkingMeta(
            narrative_enabled=narrative_enabled,
            visual_mode=visual_mode,
            generation_mode="img2img" if use_ref else "txt2img",
            img2img_denoise=denoise,
            prompt_layers=_prompt_layers_from_built(built),
        )
    return BuildPromptResponse(
        prompt=built.positive,
        display_prompt=built.display_prompt or built.positive,
        negative_prompt=built.negative,
        workflow_type=built.workflow_type,  # type: ignore[arg-type]
        truncated=built.truncated,
        segments=list(built.segments),
        parsed_fields=built.parsed_fields,
        use_visual_reference=use_ref,
        img2img_denoise=denoise,
        visual_reference_note=note,
        shot_linking=shot_linking,
        trace_id=trace_id,
    )


@router.post("/api/prompt/classify-intent", response_model=ClassifyIntentResponse)
async def api_classify_intent(
    body: ClassifyIntentRequest,
    _user: User = Depends(get_current_user),
):
    """生成前识别用户输入是剧本、单镜描述还是出图/视频提示词。"""
    try:
        result = await classify_user_intent(
            body.text.strip(),
            context=body.context,
            current_text_mode=body.current_text_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"意图识别失败: {str(exc)[:200]}",
        ) from exc
    return ClassifyIntentResponse(**result)


@router.post("/api/prompt/build", response_model=BuildPromptResponse)
def build_prompt(
    body: BuildPromptRequest,
    _user: User = Depends(get_current_user),
):
    workflow_type = _resolve_workflow_type(body.model_id)
    built = build_prompt_from_fields(
        body.fields.model_dump(),
        workflow_type,
        global_style=body.global_style,
    )
    return _to_response(built)


@router.post("/api/prompt/build-shot", response_model=BuildPromptResponse)
async def build_script_shot(
    body: BuildScriptShotRequest,
    _user: User = Depends(get_current_user),
):
    """分镜单行：用户只填 description，后端组装简洁生成 prompt + 独立 display_prompt。"""
    description = (body.description or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="请填写画面描述")

    workflow_type = _resolve_workflow_type(body.model_id)
    prior = [item.model_dump() for item in body.prior_shots]
    built = build_script_shot_prompt(
        description,
        workflow_type,
        global_style=body.global_style,
        theme_context=body.theme_context,
        prior_shots=prior,
        shot_number=body.shot_number,
        continuity_mode=body.continuity_mode,
        style_reference=body.style_reference,
        quality_preset_id=body.quality_preset_id,
    )
    prior_desc = prior[-1].get("description") if prior else None
    visual_decision = evaluate_visual_reference(
        description=description,
        prior_description=prior_desc,
        visual_continuity=body.visual_continuity,
        shot_number=body.shot_number,
        has_manual_reference=body.has_manual_reference,
        has_previous_shot_image=body.has_previous_shot_image,
    )
    narrative_on = body.continuity_mode and body.shot_number > 1
    trace_id = (body.trace_id or "").strip() or str(uuid.uuid4())
    await push_trace(
        0,
        "BUILT",
        {
            "trace_id": trace_id,
            "task_type": "image",
            "quality_preset_id": body.quality_preset_id,
            "positive": built.positive,
            "negative": built.negative,
            "display_prompt": built.display_prompt or description,
            "shot_number": body.shot_number,
        },
    )
    return _to_response(
        built,
        visual_decision=visual_decision,
        narrative_enabled=narrative_on or bool((body.theme_context or "").strip()),
        trace_id=trace_id,
    )


@router.post("/api/prompt/expand-shot-package", response_model=ExpandShotPackageResponse)
async def expand_shot_package(
    body: ExpandShotPackageRequest,
    _user: User = Depends(get_current_user),
):
    """分镜镜/格：扩写为小云雀式三层 prompt（规则兜底 + 可选 LLM）。"""
    row = body.row.model_dump()
    payload = {
        "row": {
            **row,
            "keyframes": [k.model_dump() for k in body.row.keyframes],
        },
        "cast_library": [c.model_dump() for c in body.cast_library],
        "keyframe_id": body.keyframe_id,
        "style_reference": body.style_reference,
    }
    result = await build_shot_prompt_package(payload, use_llm=body.use_llm)
    return ExpandShotPackageResponse(**result)


@router.post("/api/prompt/split-shot-beats", response_model=SplitShotBeatsResponse)
async def api_split_shot_beats(
    body: SplitShotBeatsRequest,
    _user: User = Depends(get_current_user),
):
    """根据镜级剧情与时长，LLM 拆分为连续分镜节拍（含每格出图 prompt）。"""
    row = body.row.model_dump()
    payload = {
        "row": {
            **row,
            "keyframes": [k.model_dump() for k in body.row.keyframes],
        },
        "cast_library": [c.model_dump() for c in body.cast_library],
    }
    result = await split_shot_beats(payload, use_llm=body.use_llm)
    return SplitShotBeatsResponse(**result)


@router.post(
    "/api/canvas/script-table/generate",
    response_model=ScriptTableGenerateResponse,
)
async def script_table_generate_stub(
    body: ScriptTableGenerateRequest,
    _user: User = Depends(get_current_user),
):
    workflow_type = _resolve_workflow_type(body.model_id)
    built = build_script_shot_prompt(
        body.fields.description or "",
        workflow_type,
        global_style=body.global_style,
    )
    ref_note = "（含参考图）" if (body.reference_image or "").strip() else ""
    return ScriptTableGenerateResponse(
        status="stub",
        prompt=built.positive,
        negative_prompt=built.negative,
        workflow_type=built.workflow_type,  # type: ignore[arg-type]
        truncated=built.truncated,
        message=(
            f"prompt 已就绪{ref_note}；"
            "画布将自动创建/触发关联 image-gen 节点出图"
        ),
        row_id=body.row_id,
        node_id=body.node_id,
    )
