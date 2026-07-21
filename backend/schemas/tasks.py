from typing import Literal, Optional

from pydantic import BaseModel, Field


class CanvasMention(BaseModel):
    """画布 @ 引用：节点 ID + 类型，由后端解析为参考图/上下文。"""

    id: str = Field(..., description="画布节点 ID")
    type: str = Field(..., description="image | video | text")
    name: Optional[str] = Field(default=None, description="展示名称")
    image_index: Optional[int] = Field(default=None, description="image-gen 多图索引")


class SubmitRequest(BaseModel):
    team_id: str | None = Field(default=None, description="团队上下文")
    prompt: str = Field(..., description="画面描述")
    negative_prompt: str = Field(
        default="blurry, low quality, watermark, text",
        description="不想要的元素",
    )
    style: str = Field(default="realistic", description="realistic | anime | oil")
    width: int = Field(default=512, ge=64, le=2048)
    height: int = Field(default=512, ge=64, le=2048)
    client_id: str | None = Field(default=None, description="与 WebSocket 一致的 clientId")
    auto_optimize: bool = Field(default=True, description="提交前自动优化提示词")
    reference_image: Optional[str] = Field(default=None, description="参考图 URL（服务器路径或 http URL）")


class SubmitVideoRequest(BaseModel):
    team_id: str | None = Field(default=None, description="团队上下文")
    prompt: str = Field(..., description="画面描述")
    negative_prompt: str = Field(default="", description="排除元素")
    duration: int = Field(default=5, description="视频时长秒数，3 / 5 / 10 / 15")
    width: int = Field(default=848, ge=64, le=2048)
    height: int = Field(default=480, ge=64, le=2048)
    mode: str = Field(default="text2video", description="text2video | image2video")
    image: str | None = Field(default=None, description="图生视频 base64")
    client_id: str | None = Field(default=None)
    auto_optimize: bool = Field(default=True, description="提交前自动优化提示词")


class OptimizePromptRequest(BaseModel):
    text: str = Field(..., description="用户中文描述")
    mode: str = Field(default="image", description="image 或 video")


class SelectModelRequest(BaseModel):
    type: Literal["image", "video"] = Field(..., description="image 或 video")
    model: str = Field(..., description="模型文件名，位于 checkpoints 目录")


class CanvasTextRequest(BaseModel):
    team_id: str | None = Field(default=None, description="团队上下文")
    """画布文本生成卡片请求体。
    model: LLM 供应商模型标识，如 gemini-2.5-flash / gpt-4o / claude-opus-4
    prompt: 用户输入的文本描述
    count: 生成数量，1-4
    node_id: 前端节点 ID，用于结果回填
    """

    model: str = Field(..., description="LLM 模型标识")
    prompt: str = Field(..., description="用户输入描述")
    count: int = Field(default=1, ge=1, le=4, description="生成数量")
    node_id: str = Field(..., description="前端节点 ID")
    screenplay_mode: bool = Field(
        default=False,
        description="剧本模式：附加分镜链路专用写作指令",
    )


class CanvasImageRequest(BaseModel):
    team_id: str | None = Field(default=None, description="团队上下文")
    """画布图像生成卡片请求体。
    model: 图像模型标识，如 flux-dev / hidream / jimeng-5.0-lite
    prompt: 画面描述
    reference_image: 参考图 URL（可选）
    quality: 画质等级，480P | 720P | 1080P（兼容旧值 2K/3K）
    ratio: 宽高比，如 1:1 / 16:9 / 9:16 等
    width/height: 可选显式像素；同时提供时优先于 ratio/quality
    count: 生成数量，1-4
    node_id: 前端节点 ID
    """

    model: str = Field(..., description="图像模型标识")
    prompt: str = Field(..., description="画面描述（实际提交生成用）")
    display_prompt: Optional[str] = Field(
        default=None,
        description="UI 展示用描述，仅 Trace L1 展示",
    )
    denoise: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="img2img 时覆盖 KSampler denoise",
    )
    negative_prompt: Optional[str] = Field(
        default=None,
        description="负向 prompt（分镜表等预构建 negative）",
    )
    reference_image: Optional[str] = Field(default=None, description="参考图 URL")
    reference_images: Optional[list[str]] = Field(
        default=None, description="参考图 URL 列表"
    )
    quality: str = Field(
        default="720P",
        description="画质：480P | 720P | 1080P（兼容旧值 2K/3K）",
    )
    ratio: str = Field(default="1:1", description="宽高比")
    width: Optional[int] = Field(
        default=None,
        ge=64,
        le=4096,
        description="显式宽度；与 height 同时提供时优先",
    )
    height: Optional[int] = Field(
        default=None,
        ge=64,
        le=4096,
        description="显式高度；与 width 同时提供时优先",
    )
    count: int = Field(default=1, ge=1, le=4, description="生成数量")
    node_id: str = Field(..., description="前端节点 ID")
    mentions: Optional[list[CanvasMention]] = Field(
        default=None, description="@ 引用的画布节点"
    )
    trace_id: Optional[str] = Field(
        default=None, description="Prompt Trace 会话 ID"
    )
    quality_preset_id: Optional[str] = Field(
        default=None, description="画风预设 ID（trace 展示用）"
    )
    project_id: Optional[str] = Field(
        default=None, description="画布项目 ID，用于解析 @mentions"
    )
    use_reactor: bool = Field(
        default=False,
        description="G40：flux-pulid 出图后接 ReActor 单帧换脸（需角色正脸参考图）",
    )
    identity_ids: list[str] | None = Field(
        default=None,
        description="本镜绑定的 identityId 列表（任务审计）",
    )
    entity_ref_audit: list[dict] | None = Field(
        default=None,
        description="角色参考图注入审计",
    )


class CanvasVideoRequest(BaseModel):
    team_id: str | None = Field(default=None, description="团队上下文")
    """画布视频生成卡片请求体。
    model: 视频模型标识，如 wan-2.6 / ltx-video / seedance-2.0
    prompt: 画面描述
    generation_mode: 生成方式，首尾帧 | 参考
    ratio: 宽高比，16:9 | 9:16 | 1:1
    resolution: 清晰度，720P | 1080P
    duration: 时长（秒），5 | 10 | 15
    audio: 是否生成音频
    count: 生成数量（当前仅支持 1，批量视频未实现）
    node_id: 前端节点 ID
    """

    model: str = Field(..., description="视频模型标识")
    prompt: str = Field(..., description="画面描述")
    generation_mode: str = Field(default="keyframe", description="keyframe | freeref")
    ratio: str = Field(default="16:9", description="宽高比")
    resolution: str = Field(default="720P", description="清晰度：480P | 720P | 1080P")
    duration: int = Field(default=5, description="时长（秒）：5 | 10 | 15")
    audio: bool = Field(default=False, description="是否生成音频")
    count: int = Field(default=1, ge=1, le=1, description="生成数量（仅支持 1）")
    node_id: str = Field(..., description="前端节点 ID")
    reference_image: Optional[str] = Field(default=None, description="参考图 URL（兼容）")
    first_frame: Optional[str] = Field(default=None, description="首帧图片 URL")
    last_frame: Optional[str] = Field(default=None, description="尾帧图片 URL")
    reference_images: Optional[list[str]] = Field(default=None, description="全能参考模式图片 URL 列表")
    mentions: Optional[list[CanvasMention]] = Field(
        default=None, description="@ 引用的画布节点"
    )
    client_id: Optional[str] = Field(
        default=None,
        description="与前端 WebSocket 一致的 clientId，用于接收 ComfyUI 进度推送",
    )
    trace_id: Optional[str] = Field(
        default=None, description="Prompt Trace 会话 ID"
    )
    quality_preset_id: Optional[str] = Field(
        default=None, description="画风预设 ID（注入 prompt suffix）"
    )
    project_id: Optional[str] = Field(
        default=None, description="画布项目 ID，用于解析 @mentions"
    )
    sampling_profile: Optional[Literal["fast", "quality"]] = Field(
        default="quality",
        description="采样档位：Wan fast=4步/quality=8步；LTX2 默认 quality",
    )
    camera_move: Optional[str] = Field(
        default="auto",
        description="G33/G36 运镜：auto|push_in|pull_out|pan|track|static",
    )
    shot_scale: Optional[str] = Field(
        default="auto",
        description="G33/G36 景别：auto|close|medium|wide|full",
    )
    sound_note: Optional[str] = Field(
        default=None,
        description="G39 音效备注；非空且非 ltx2 时成片后混入 AudioGen 音效",
    )
    use_reactor: bool = Field(
        default=False,
        description="G45：成片后逐帧 ReActor 换脸（需 reactor_face_image 正脸参考）",
    )
    reactor_face_image: Optional[str] = Field(
        default=None,
        description="G45：换脸源正脸图 URL（/api/uploads/... 或 /api/view?...）",
    )
    steps: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="可选采样步数（探针/高级覆盖）",
    )
    use_cache: Optional[bool] = Field(
        default=None,
        description="保留字段（历史兼容；当前未使用）",
    )
    identity_ids: Optional[list[str]] = Field(
        default=None,
        description="本镜绑定的 identityId 列表（任务审计）",
    )
    entity_ref_audit: Optional[list[dict]] = Field(
        default=None,
        description="角色参考图注入审计",
    )
    width: Optional[int] = Field(
        default=None,
        ge=64,
        le=2048,
        description="可选宽度；与 height 同时提供时跳过 RESOLUTION_MAP（探针用）",
    )
    height: Optional[int] = Field(
        default=None,
        ge=64,
        le=2048,
        description="可选高度；与 width 同时提供时跳过 RESOLUTION_MAP（探针用）",
    )


class VideoEnhanceRequest(BaseModel):
    team_id: str | None = Field(default=None, description="团队上下文")
    video_url: str = Field(..., description="待增强视频 URL（/api/uploads/videos/... 或带 ticket）")
    upscale_factor: float = Field(
        default=2.0,
        description="超分倍数：1.0（仅增强）/ 1.5 / 2.0 / 3.0",
    )
    workflow: Literal["auto", "seedvr2", "realesrgan"] = Field(
        default="auto",
        description="增强 workflow；auto 时 SeedVR2 优先",
    )
    strength: Literal["normal", "sharp"] = Field(
        default="normal",
        description="增强强度（SeedVR2 模型变体）",
    )
    input_noise_scale: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="SeedVR2 输入噪点强度",
    )
    batch_size: int = Field(default=8, description="SeedVR2 时序批次：4 / 8 / 16")
    color_correction: Literal["lab", "none"] = Field(
        default="lab",
        description="SeedVR2 色彩校正",
    )
    model_size: Literal["3b", "7b"] = Field(
        default="7b",
        description="SeedVR2 DiT 规模；默认 7b（H800 顶配 FP16）",
    )
    node_id: str | None = Field(default=None, description="前端 video-gen 节点 ID")
    client_id: Optional[str] = Field(
        default=None,
        description="与前端 WebSocket 一致的 clientId",
    )
    trace_id: Optional[str] = Field(
        default=None, description="Prompt Trace 会话 ID"
    )


class VideoEnhanceRecommendRequest(BaseModel):
    video_url: str = Field(..., description="待分析视频 URL")
    project_id: Optional[str] = Field(default=None, description="画布项目 ID")
    script_table_node_id: Optional[str] = Field(
        default=None, description="分镜表节点 ID（读取 defaultQualityPresetId）"
    )


class VideoEnhanceRecommendResponse(BaseModel):
    params: dict
    reasoning: str


class ImageEnhanceRequest(BaseModel):
    image_url: str = Field(..., description="待增强静帧 URL")
    upscale_factor: float = Field(default=2.0, description="1.0 / 1.5 / 2.0 / 3.0")
    strength: Literal["normal", "sharp"] = Field(default="normal")
    input_noise_scale: float = Field(default=0.25, ge=0.0, le=1.0)
    color_correction: Literal["lab", "none"] = Field(default="lab")
    model_size: Literal["3b", "7b"] = Field(
        default="7b",
        description="SeedVR2 DiT 规模；默认 7b FP16 顶配",
    )
    node_id: str | None = Field(default=None, description="前端 image-gen 节点 ID")
    project_id: Optional[str] = Field(default=None, description="画布项目 ID")
    team_id: Optional[str] = Field(default=None)
    client_id: Optional[str] = Field(default=None)
    trace_id: Optional[str] = Field(default=None)


class VideoLutRequest(BaseModel):
    video_url: str = Field(..., description="原始视频 URL")
    node_id: Optional[str] = Field(default=None, description="视频生成节点 ID")
    project_id: str = Field(..., description="画布项目 ID")
    script_table_node_id: str = Field(..., description="分镜表节点 ID")
    team_id: Optional[str] = Field(default=None)
    trace_id: Optional[str] = Field(
        default=None, description="Prompt Trace 会话 ID"
    )


class TaskRatingRequest(BaseModel):
    rating: int = Field(..., description="1=满意 0=不满意")
    tags: list[str] = Field(default_factory=list, description="不满意原因标签")
    comment: str | None = Field(default=None, description="不满意补充说明")
