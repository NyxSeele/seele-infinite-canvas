from typing import Literal, Optional

from pydantic import BaseModel, Field


class PromptFields(BaseModel):
    """节点字段：用户输入仅作为 prompt 文本，不含路径或模型文件名。"""

    description: str = Field(default="", description="镜头/画面描述")
    character: str = Field(default="", description="角色")
    scene: str = Field(default="", description="场景")
    style: str = Field(default="", description="风格")
    camera: str = Field(default="", description="镜头/景别")
    action: str = Field(default="", description="动作")
    lighting: str = Field(default="", description="光线")
    extra: str = Field(default="", description="补充说明")
    unwanted: str = Field(default="", description="不想要的元素（仅 SD 系 negative）")


class PriorShotContext(BaseModel):
    shot_number: int = Field(default=1, ge=1)
    description: str = Field(default="")


class BuildPromptRequest(BaseModel):
    fields: PromptFields = Field(default_factory=PromptFields)
    model_id: str = Field(..., description="图像模型 ID，由后端解析 workflow_type")
    global_style: str = Field(default="", description="全局风格（可选）")


class BuildScriptShotRequest(BaseModel):
    """分镜单行：用户只填 description，结构化字段由后端推断。"""

    description: str = Field(..., description="镜头画面描述（单输入框）")
    model_id: str = Field(..., description="图像模型 ID")
    global_style: str = Field(default="", description="全局风格")
    theme_context: str = Field(
        default="",
        description="主题/角色/世界观统一设定，保证多镜头连贯",
    )
    prior_shots: list[PriorShotContext] = Field(
        default_factory=list,
        description="当前镜头之前的分镜描述",
    )
    shot_number: int = Field(default=1, ge=1)
    visual_continuity: bool = Field(
        default=False,
        description="是否开启「视觉参考上一镜」（由前端传入，用于策略判断）",
    )
    has_previous_shot_image: bool = Field(
        default=False,
        description="上一镜是否已有成片 URL（由前端传入）",
    )
    continuity_mode: bool = Field(
        default=True,
        description="剧情连贯：主题 + 承接上一镜描述写入 generation prompt",
    )
    has_manual_reference: bool = Field(
        default=False,
        description="本镜是否已上传手动参考图",
    )
    style_reference: Optional[dict] = Field(
        default=None,
        description="项目级视频风格参考（结构化 JSON）",
    )
    quality_preset_id: str = Field(
        default="auto",
        description="画风预设 ID（与分镜表 qualityPresetId 对齐）",
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="Prompt Trace 会话 ID（可选，由前端传入以串联 L0–L4）",
    )
    character_refs_count: int = Field(
        default=0,
        ge=0,
        description="compile 阶段传入的角色引用数量（供 L0 trace 日志）",
    )
    cast_library: list[dict] = Field(
        default_factory=list,
        description="分镜表角色库（identity 门禁用）",
    )
    identity_ids: list[str] = Field(
        default_factory=list,
        description="本镜绑定的 identityId 列表",
    )
    row: Optional[dict] = Field(
        default=None,
        description="分镜行快照（含 identityIds / promptMentions）",
    )


class ShotLinkingMeta(BaseModel):
    """分镜镜头关联说明：剧情 prompt 层 vs 视觉 img2img 层。"""

    narrative_enabled: bool = Field(
        description="是否在 prompt 中注入主题/上一镜剧情"
    )
    visual_mode: str = Field(
        description="none | continuity | new_subject | manual | no_prior_image"
    )
    generation_mode: str = Field(description="txt2img | img2img")
    img2img_denoise: Optional[float] = None
    prompt_layers: list[str] = Field(
        default_factory=list,
        description="写入 generation prompt 的层次，如 theme / prior_shot / shot / style_en",
    )


class BuildPromptResponse(BaseModel):
    prompt: str
    display_prompt: str = Field(default="", description="UI 展示用，不含内部连贯性注入")
    negative_prompt: str
    workflow_type: Literal["sd15", "sdxl", "flux"]
    truncated: bool
    segments: list[str]
    parsed_fields: Optional[dict] = None
    use_visual_reference: bool = Field(
        default=False,
        description="是否建议使用上一镜成片作 img2img",
    )
    img2img_denoise: Optional[float] = Field(
        default=None,
        description="img2img 时建议 denoise（0–1）",
    )
    visual_reference_note: Optional[str] = Field(
        default=None,
        description="视觉参考策略说明（供 UI 提示）",
    )
    shot_linking: Optional[ShotLinkingMeta] = None
    trace_id: Optional[str] = Field(
        default=None,
        description="Prompt Trace 会话 ID（回显）",
    )


class CharacterRefPayload(BaseModel):
    name: str = ""
    appearance: str = Field(default="", description="外貌/人设描述")
    desc: str = Field(default="", description="兼容旧字段")


class CompilePromptRequest(BaseModel):
    scene_desc: str = Field(default="", description="分镜/场景描述")
    character_refs: list[CharacterRefPayload] = Field(default_factory=list)
    style_preset: str = Field(default="", description="画风预设 id 或名称")
    model_target: Literal["flux", "wan-t2v", "wan-i2v", "seedance"] = "flux"
    trace_id: Optional[str] = Field(
        default=None,
        description="Prompt Trace 会话 ID（与 build-shot 串联 L0 COMPILED / BUILT）",
    )
    camera_move: Optional[str] = Field(
        default="auto",
        description="G33 显式运镜：auto|push_in|pull_out|pan|track|static",
    )
    shot_scale: Optional[str] = Field(
        default="auto",
        description="G33 显式景别：auto|close|medium|wide|full",
    )


class CompilePromptResponse(BaseModel):
    positive_prompt: str
    negative_prompt: str
    model_params: dict


class ScriptTableGenerateRequest(BaseModel):
    node_id: str = Field(..., description="画布分镜表节点 ID")
    row_id: str = Field(..., description="分镜行 ID")
    model_id: str = Field(..., description="图像模型 ID")
    fields: PromptFields = Field(default_factory=PromptFields)
    global_style: str = Field(default="", description="分镜表全局风格")
    reference_image: Optional[str] = Field(
        default=None,
        description="参考图 URL（仅透传记录，stub 阶段不出图）",
    )


class ShotKeyframePayload(BaseModel):
    id: str = ""
    label: str = ""
    time_start: float = 0
    time_end: float = 0
    prompt: str = ""
    reference_image: Optional[str] = None


class ShotRowPayload(BaseModel):
    id: str = ""
    shot_number: int = 1
    duration: float = 8
    prompt: str = ""
    sound_note: str = ""
    atmosphere_note: str = ""
    camera: str = ""
    movement: str = ""
    lighting: str = ""
    composition: str = ""
    color_grade: str = ""
    lens: str = ""
    performance: str = ""
    sound_design: str = ""
    keyframes: list[ShotKeyframePayload] = Field(default_factory=list)


class CastItemPayload(BaseModel):
    name: str = ""
    type: str = "character"


class SceneItemPayload(BaseModel):
    id: Optional[str] = None
    name: str = ""
    type: str = "scene"


class ExpandShotPackageRequest(BaseModel):
    row: ShotRowPayload
    cast_library: list[CastItemPayload] = Field(default_factory=list)
    scene_library: list[SceneItemPayload] = Field(default_factory=list)
    keyframe_id: Optional[str] = Field(
        default=None,
        description="仅扩写单格时传入",
    )
    use_llm: bool = Field(default=True, description="是否尝试 LLM 扩写")
    style_reference: Optional[dict] = Field(
        default=None,
        description="项目级视频风格参考",
    )


class ExpandShotPackageResponse(BaseModel):
    basic: str
    atmosphere: str
    frames: str
    full_text: str
    api_description: str
    source: Literal["rule", "llm"] = "rule"


class ShotBeatItem(BaseModel):
    label: str = ""
    time_start: float = 0
    time_end: float = 0
    prompt: str = ""
    prompt_en: str = Field(default="", description="英文画面描述，供图像/视频 API")
    action_note: str = ""


class SplitShotBeatsRequest(BaseModel):
    row: ShotRowPayload
    cast_library: list[CastItemPayload] = Field(default_factory=list)
    scene_library: list[SceneItemPayload] = Field(default_factory=list)
    use_llm: bool = Field(default=True, description="是否用 LLM 拆分节拍")


class SplitShotBeatsResponse(BaseModel):
    beats: list[ShotBeatItem]
    source: Literal["rule", "llm"] = "rule"
    duration: float = 8


class ScriptTableGenerateResponse(BaseModel):
    status: Literal["stub"] = "stub"
    prompt: str
    negative_prompt: str
    workflow_type: Literal["sd15", "sdxl", "flux"]
    truncated: bool
    message: str
    row_id: str
    node_id: str
