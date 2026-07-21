import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from core.dependencies import user_from_access_token
from services.canvas_access import get_accessible_project
from db.session import SessionLocal
from services.canvas_lock import event_channel
from services.canvas_presence import leave_presence, touch_presence
from services.canvas_ws_messages import handle_client_message
from services.user_profile import presence_meta_for_user, presence_meta_for_user_id
from services.canvas_ws_hub import broadcast_json, register, unregister
from services.project_collaborators import touch_collaborator_throttled
from services.redis_client import get_redis

router = APIRouter(tags=["canvas-ws"])


def _extract_token(websocket: WebSocket) -> str:
    return (websocket.query_params.get("token") or "").strip()


@router.websocket("/ws/canvas/{project_id}")
async def canvas_events_ws(websocket: WebSocket, project_id: str):
    token = _extract_token(websocket)
    db = SessionLocal()
    try:
        user = user_from_access_token(token, db)
        get_accessible_project(db, user, project_id)
    except HTTPException as exc:
        code = 4403 if exc.status_code == 403 else 4404 if exc.status_code == 404 else 4401
        reason = exc.detail if isinstance(exc.detail, str) else "无权访问"
        await websocket.close(code=code, reason=reason or "无权访问")
        return
    except Exception:
        await websocket.close(code=4401, reason="未授权")
        return
    finally:
        db.close()

    await websocket.accept()
    register(project_id, websocket)
    user_id = int(user.id)
    username = user.username or str(user_id)

    avatar_url, display_name, email = presence_meta_for_user(user)
    members = touch_presence(
        project_id,
        user_id,
        username,
        is_editor=False,
        avatar_url=avatar_url,
        display_name=display_name,
        email=email,
    )
    touch_collaborator_throttled(project_id, user_id)
    try:
        await websocket.send_json(
            {"type": "presence_changed", "project_id": project_id, "members": members}
        )
    except Exception:
        pass

    r = get_redis()
    if r is None:
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "presence_ping":
                    av, label, email = presence_meta_for_user_id(user_id)
                    members = touch_presence(
                        project_id,
                        user_id,
                        str(msg.get("username") or username),
                        is_editor=bool(msg.get("is_editor")),
                        avatar_url=av,
                        display_name=label,
                        email=email,
                    )
                    touch_collaborator_throttled(project_id, user_id)
                    await broadcast_json(
                        project_id,
                        {
                            "type": "presence_changed",
                            "project_id": project_id,
                            "members": members,
                        },
                    )
                elif msg.get("type") == "presence_leave":
                    members = leave_presence(project_id, user_id)
                    await broadcast_json(
                        project_id,
                        {
                            "type": "presence_changed",
                            "project_id": project_id,
                            "members": members,
                        },
                    )
                else:
                    handle_client_message(project_id, user, msg)
        except WebSocketDisconnect:
            pass
        finally:
            leave_presence(project_id, user_id)
            unregister(project_id, websocket)
        return

    pubsub = r.pubsub()
    channel = event_channel(project_id)
    pubsub.subscribe(channel)

    async def pump_redis():
        while True:
            message = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
            if not message or message.get("type") != "message":
                await asyncio.sleep(0.05)
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="ignore")
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                payload = {"type": "raw", "data": data}
            await websocket.send_json(payload)

    async def pump_client():
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "presence_ping":
                    av, label, email = presence_meta_for_user_id(user_id)
                    members = touch_presence(
                        project_id,
                        user_id,
                        str(msg.get("username") or username),
                        is_editor=bool(msg.get("is_editor")),
                        avatar_url=av,
                        display_name=label,
                        email=email,
                    )
                    touch_collaborator_throttled(project_id, user_id)
                    await websocket.send_json(
                        {
                            "type": "presence_changed",
                            "project_id": project_id,
                            "members": members,
                        }
                    )
                elif msg.get("type") == "presence_leave":
                    members = leave_presence(project_id, user_id)
                    await websocket.send_json(
                        {
                            "type": "presence_changed",
                            "project_id": project_id,
                            "members": members,
                        }
                    )
                else:
                    handle_client_message(project_id, user, msg)
        except WebSocketDisconnect:
            pass

    pump_task = asyncio.create_task(pump_redis())
    client_task = asyncio.create_task(pump_client())
    done, pending = await asyncio.wait(
        [pump_task, client_task], return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending:
        t.cancel()
    try:
        pubsub.unsubscribe(channel)
        pubsub.close()
    except Exception:
        pass
    for t in done:
        try:
            await t
        except Exception:
            pass
    leave_presence(project_id, user_id)
    unregister(project_id, websocket)
