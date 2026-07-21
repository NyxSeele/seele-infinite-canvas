import asyncio
import json
import uuid
from urllib.parse import parse_qs

import websockets
from websockets.exceptions import InvalidURI, WebSocketException
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from core.comfyui_settings import comfyui_nodes_list, comfyui_ws_url_for_node
from db.session import SessionLocal

router = APIRouter(tags=["websocket"])

_COMFY_NOT_RUNNING_ERRORS = (
    ConnectionRefusedError,
    OSError,
    WebSocketException,
    InvalidURI,
)


def _extract_ws_token(websocket: WebSocket) -> str:
    token = (websocket.query_params.get("token") or "").strip()
    if token:
        return token
    raw = websocket.scope.get("query_string") or b""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    parsed = parse_qs(raw, keep_blank_values=False)
    for key in ("token", "Token"):
        vals = parsed.get(key)
        if vals and str(vals[0]).strip():
            return str(vals[0]).strip()
    return ""


async def _relay_comfy_to_client(comfy_ws, websocket: WebSocket, client_id: str) -> None:
    from services import comfyui_progress

    async for message in comfy_ws:
        if websocket.client_state.name != "CONNECTED":
            break
        if isinstance(message, bytes):
            try:
                await websocket.send_bytes(message)
            except (RuntimeError, WebSocketDisconnect):
                break
            continue
        outbound = message
        try:
            payload = json.loads(message)
            msg_type = payload.get("type")
            d = payload.get("data") or {}

            if msg_type in ("execution_start", "executing"):
                pid = d.get("prompt_id")
                if pid:
                    comfyui_progress.set_active_prompt(client_id, str(pid))

            if msg_type == "progress" and "value" in d and "max" in d:
                pid = comfyui_progress.resolve_prompt_id(client_id, d)
                if pid:
                    comfyui_progress.record_progress(
                        pid,
                        d.get("value", 0),
                        d.get("max", 0),
                        node=d.get("node"),
                    )
                    row = comfyui_progress.get_progress(pid)
                    if row and row.get("progress") is not None:
                        d = dict(d)
                        d["progress"] = row["progress"]
                        payload["data"] = d
                        outbound = json.dumps(payload)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        try:
            await websocket.send_text(outbound)
        except (RuntimeError, WebSocketDisconnect):
            break


@router.websocket("/ws")
async def websocket_proxy(websocket: WebSocket):
    token = _extract_ws_token(websocket)
    db = SessionLocal()
    try:
        from core.dependencies import user_from_access_token

        user = user_from_access_token(token, db)
    except HTTPException:
        await websocket.close(code=4401, reason="未授权")
        return
    finally:
        db.close()

    await websocket.accept()
    client_id = websocket.query_params.get("clientId") or str(uuid.uuid4())
    node_urls = comfyui_nodes_list()

    comfy_connections: list = []
    try:
        for node_url in node_urls:
            comfy_uri = f"{comfyui_ws_url_for_node(node_url)}?clientId={client_id}"
            try:
                comfy_ws = await websockets.connect(
                    comfy_uri,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                )
                comfy_connections.append(comfy_ws)
            except _COMFY_NOT_RUNNING_ERRORS as exc:
                print(f"ComfyUI WS 连接失败 node={node_url} user={user.id}: {exc}")

        if not comfy_connections:
            raise ConnectionRefusedError("所有 ComfyUI 节点均无法连接")

        async def recv_from_client():
            try:
                if hasattr(websocket, "iter_text"):
                    async for message in websocket.iter_text():
                        for comfy_ws in comfy_connections:
                            await comfy_ws.send(message)
                else:
                    while True:
                        message = await websocket.receive_text()
                        for comfy_ws in comfy_connections:
                            await comfy_ws.send(message)
            except (WebSocketDisconnect, Exception):
                pass

        relay_tasks = [
            asyncio.create_task(_relay_comfy_to_client(ws, websocket, client_id))
            for ws in comfy_connections
        ]
        client_task = asyncio.create_task(recv_from_client())
        done, pending = await asyncio.wait(
            [*relay_tasks, client_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except _COMFY_NOT_RUNNING_ERRORS as e:
        print(f"ComfyUI 未启动或连接失败 (user={user.id}): {e}")
        if websocket.client_state.name == "CONNECTED":
            try:
                await websocket.send_json(
                    {"type": "error", "message": "ComfyUI 未启动或无法连接"}
                )
            except Exception:
                pass
    except Exception as e:
        print(f"WebSocket 代理异常 (user={user.id}): {e}")
    finally:
        for comfy_ws in comfy_connections:
            try:
                await comfy_ws.close()
            except Exception:
                pass
        if websocket.client_state.name == "CONNECTED":
            try:
                await websocket.close()
            except Exception:
                pass
