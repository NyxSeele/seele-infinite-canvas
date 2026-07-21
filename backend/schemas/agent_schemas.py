from pydantic import BaseModel, Field
from typing import Any, Optional, List, Dict


class CanvasNodeSnapshot(BaseModel):
    id: str
    type: str
    position: Dict[str, float]
    content_preview: str
    label: Optional[str] = None
    text_mode: Optional[str] = None
    intent: Optional[str] = None
    status: Optional[str] = None
    loading: Optional[bool] = None
    scene_count: Optional[int] = None
    source_outline_id: Optional[str] = None
    linked_script_table_id: Optional[str] = None
    cast_library: Optional[List[Dict[str, Any]]] = None
    characters_preview: Optional[List[str]] = None
    row_count: Optional[int] = None
    rows_summary: Optional[List[Dict[str, Any]]] = None


class CanvasEdgeSnapshot(BaseModel):
    source: str
    target: str


class CanvasSnapshot(BaseModel):
    nodes: List[CanvasNodeSnapshot]
    edges: List[CanvasEdgeSnapshot]
    selected_node_ids: List[str] = Field(default_factory=list)
    total_node_count: int
    snapshot_truncated: bool = False
    omitted_node_count: int = 0


class AgentMessage(BaseModel):
    role: str
    content: str


class AgentRunRequest(BaseModel):
    project_id: str
    canvas_snapshot: CanvasSnapshot
    messages: List[AgentMessage]
    execution_mode: str = "manual"


class AgentCreativeOption(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    label: Optional[str] = None
    tag: Optional[str] = None
    description: Optional[str] = None
    focus: Optional[str] = None


class AgentStoredMessage(BaseModel):
    role: str
    content: str
    kind: Optional[str] = None
    roundId: Optional[str] = None
    canUndo: Optional[bool] = None
    thinking: Optional[str] = None
    creativeOptions: Optional[List[AgentCreativeOption]] = None
    creativeGroupTitle: Optional[str] = None
    creativeGroupSubtitle: Optional[str] = None
    suggestions: Optional[List[str]] = None
    castPending: Optional[List[Dict[str, Any]]] = None
    castPendingScriptTableId: Optional[str] = None


class AgentConversationSaveRequest(BaseModel):
    messages: List[AgentStoredMessage]


class AgentConversationResponse(BaseModel):
    project_id: str
    messages: List[AgentStoredMessage]


class AgentChatArchiveEntry(BaseModel):
    id: str
    project_id: str
    title: str
    messages: List[AgentStoredMessage]
    updated_at: Optional[str] = None
    updatedAt: Optional[int] = None
    message_count: Optional[int] = None


class AgentChatArchiveListResponse(BaseModel):
    project_id: str
    entries: List[AgentChatArchiveEntry]


class AgentChatArchiveSaveRequest(BaseModel):
    messages: List[AgentStoredMessage]
    id: Optional[str] = None
    title: Optional[str] = None


class AgentChatTitleRequest(BaseModel):
    messages: List[AgentStoredMessage]


class AgentChatTitleResponse(BaseModel):
    title: str


class PipelineStageResponse(BaseModel):
    name: str
    order: int
    phase: str
    optional: bool
    skill: Optional[str] = None
    executor: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    ui_label: Optional[str] = None
    preconditions: List[str] = Field(default_factory=list)
    produces: List[str] = Field(default_factory=list)
    prompt_label: str


class PipelineManifestResponse(BaseModel):
    name: str
    version: str
    description: str
    shared_skill: Optional[str] = None
    stages: List[PipelineStageResponse]
