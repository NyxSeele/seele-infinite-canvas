"""开发环境 Prompt Trace SSE 流。"""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from trace_bus import get_trace_queue

router = APIRouter(tags=["debug"])


@router.get("/api/debug/trace/stream")
async def trace_stream():
    queue = get_trace_queue()

    async def event_generator():
        while True:
            item = await queue.get()
            payload = {
                "layer": item["layer"],
                "tag": item["tag"],
                "ts": item["ts"],
                "data": item["data"],
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
