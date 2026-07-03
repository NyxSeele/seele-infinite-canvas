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
        default="模糊, 低质量, 水印, 文字",
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
    duration: int = Field(default=5, description="视频时长秒数，3 或 5")
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
    quality: 画质等级，2K | 3K
    ratio: 宽高比，如 1:1 / 16:9 / 9:16 等
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
    quality: str = Field(default="2K", description="画质：2K | 3K")
    ratio: str = Field(default="1:1", description="宽高比")
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


class CanvasVideoRequest(BaseModel):
    team_id: str | None = Field(default=None, description="团队上下文")
    """画布视频生成卡片请求体。
    model: 视频模型标识，如 wan-2.6 / ltx-video / hunyuan-video
    prompt: 画面描述
    generation_mode: 生成方式，首尾帧 | 参考
    ratio: 宽高比，16:9 | 9:16 | 1:1
    resolution: 清晰度，720P | 1080P
    duration: 时长（秒），5 | 10 | 15
    audio: 是否生成音频
    count: 生成数量，1-4
    node_id: 前端节点 ID
    """

    model: str = Field(..., description="视频模型标识")
    prompt: str = Field(..., description="画面描述")
    generation_mode: str = Field(default="keyframe", description="keyframe | freeref")
    ratio: str = Field(default="16:9", description="宽高比")
    resolution: str = Field(default="1080P", description="清晰度：720P | 1080P")
    duration: int = Field(default=5, description="时长（秒）：5 | 10 | 15")
    audio: bool = Field(default=False, description="是否生成音频")
    count: int = Field(default=1, ge=1, le=4, description="生成数量")
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
        description="SeedVR2 DiT 模型规模",
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


class VideoLutRequest(BaseModel):
    video_url: str = Field(..., description="原始视频 URL")
    node_id: Optional[str] = Field(default=None, description="视频生成节点 ID")
    project_id: str = Field(..., description="画布项目 ID")
    script_table_node_id: str = Field(..., description="分镜表节点 ID")
    team_id: Optional[str] = Field(default=None)
    trace_id: Optional[str] = Field(
        default=None, description="Prompt Trace 会话 ID"
    )
