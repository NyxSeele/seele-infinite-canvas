"""Admin feedback aggregation, analysis, trends."""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.datetime_utils import to_utc_iso
from models import Task
from models.feedback_analysis_run import FeedbackAnalysisRun
from services import mock_generation
from services.feedback_vision import build_vision_samples
from services.media_access import append_media_ticket, grant_output_access, issue_media_ticket
from services.qwen import call_feedback_analysis_llm
from services.task_generation_params import parse_generation_params

ANALYZE_SYSTEM_PROMPT = (
    "你是一个 AI 视频/图像生成系统的 Prompt 优化专家。\n"
    "分析用户反馈数据，找出规律，输出结构化优化建议。\n"
    "消息中会附上若干「样本说明文字 + 对应生成结果图片」配对；你必须逐条对照画面与 prompt，"
    "不能仅凭标签或聚合统计下结论。\n"
    "对满意样本，归纳可复用的 prompt 模式；对不满意样本，诊断 prompt 与画面的差距。"
)

ANALYZE_USER_PROMPT_TEMPLATE = """以下是 AI Studio 最近的生成反馈聚合数据（JSON）：
{aggregated}

请分析：
1. 哪些 prompt 模式在各模型上满意率高？列出3-5条规律
2. 不满意的记录里最常见的问题是什么？
3. 针对每个模型，给出具体的 prompt 改进建议
4. 必须结合附带的「样本说明 + 图片」逐条对照：画面上可见的问题是否与标签、prompt 一致
5. 用中文回答，按模型分段输出

文末必须附加一个 JSON 代码块，格式：
```json
{{"issues":[],"good_patterns":[],"actions":[],"per_sample":[]}}
```
其中 per_sample 每项结构：
{{"task_id":"","visual_issues":[],"prompt_diagnosis":"","suggested_prompt_patch":"","param_hints":[]}}
per_sample 应覆盖你分析过的每个附图样本（task_id 与样本说明一致）。"""


def effective_model_id(task: Task) -> str:
    if task.model_id:
        return task.model_id
    if task.video_backend:
        return task.video_backend
    return "unknown"


def parse_rating_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if x]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def is_mock_task(task: Task) -> bool:
    if task.comfyui_prompt_id == mock_generation.MOCK_PROMPT_ID:
        return True
    params = parse_generation_params(task.generation_params)
    return bool(params.get("mock"))


def _parse_dt(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    raw = value.strip()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def rated_tasks_query(db: Session, *, exclude_mock: bool = True):
    query = db.query(Task).filter(Task.user_rating.isnot(None))
    if exclude_mock:
        query = query.filter(
            (Task.comfyui_prompt_id.is_(None))
            | (Task.comfyui_prompt_id != mock_generation.MOCK_PROMPT_ID)
        )
    return query


def _apply_time_filters(query, since: str | None, until: str | None):
    since_dt = _parse_dt(since)
    until_dt = _parse_dt(until)
    if since_dt:
        query = query.filter(Task.rated_at >= since_dt)
    if until_dt:
        query = query.filter(Task.rated_at <= until_dt)
    return query


def result_url_for_admin(task: Task, admin_user_id: int) -> str | None:
    raw = (task.result or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    path = raw if raw.startswith("/") else f"/{raw}"
    grant_output_access(admin_user_id, path)
    ticket = issue_media_ticket(admin_user_id)["media_ticket"]
    return append_media_ticket(path, ticket)


def build_feedback_stats(
    db: Session,
    *,
    since: str | None = None,
    until: str | None = None,
    task_type: str | None = None,
) -> dict:
    query = rated_tasks_query(db)
    query = _apply_time_filters(query, since, until)
    if task_type and task_type.strip():
        query = query.filter(Task.task_type == task_type.strip())
    rows = query.all()
    rows = [t for t in rows if not is_mock_task(t)]

    total = len(rows)
    satisfied = sum(1 for t in rows if t.user_rating == 1)
    unsatisfied = sum(1 for t in rows if t.user_rating == 0)

    by_model_raw: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "satisfied": 0}
    )
    tag_counter: Counter[str] = Counter()
    tag_by_model: dict[str, Counter[str]] = defaultdict(Counter)
    unsatisfied_tag_lists: list[list[str]] = []

    for task in rows:
        mid = effective_model_id(task)
        by_model_raw[mid]["total"] += 1
        if task.user_rating == 1:
            by_model_raw[mid]["satisfied"] += 1
        tags = parse_rating_tags(task.rating_tags)
        for tag in tags:
            tag_counter[tag] += 1
            if task.user_rating == 0:
                tag_by_model[mid][tag] += 1
        if task.user_rating == 0 and tags:
            unsatisfied_tag_lists.append(tags)

    co_counter: Counter[tuple[str, str]] = Counter()
    for tags in unsatisfied_tag_lists:
        unique = sorted(set(tags))
        for a, b in combinations(unique, 2):
            co_counter[(a, b)] += 1

    by_model = []
    for model_id, stats in by_model_raw.items():
        model_total = stats["total"]
        model_satisfied = stats["satisfied"]
        rate = round(model_satisfied / model_total, 2) if model_total else 0.0
        by_model.append(
            {
                "model_id": model_id,
                "total": model_total,
                "satisfied": model_satisfied,
                "rate": rate,
            }
        )
    by_model.sort(key=lambda x: x["rate"])

    tag_cooccurrence = [
        {"tags": [a, b], "count": count}
        for (a, b), count in co_counter.most_common(20)
    ]

    return {
        "total": total,
        "satisfied": satisfied,
        "unsatisfied": unsatisfied,
        "by_model": by_model,
        "tag_counts": dict(tag_counter),
        "tag_counts_by_model": {
            mid: dict(counter) for mid, counter in tag_by_model.items()
        },
        "tag_cooccurrence": tag_cooccurrence,
    }


def serialize_feedback_record(task: Task, admin_user_id: int | None = None) -> dict:
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "model_id": effective_model_id(task),
        "original_input": task.original_input,
        "compiled_prompt": task.compiled_prompt,
        "user_rating": task.user_rating,
        "rating_tags": parse_rating_tags(task.rating_tags),
        "rating_comment": task.rating_comment,
        "generation_params": parse_generation_params(task.generation_params),
        "result": task.result,
        "result_url": result_url_for_admin(task, admin_user_id) if admin_user_id else None,
        "rated_at": to_utc_iso(task.rated_at) if task.rated_at else None,
        "completed_at": to_utc_iso(task.completed_at) if task.completed_at else None,
        "generation_seconds": task.generation_seconds,
    }


def list_feedback_records(
    db: Session,
    *,
    rating: int | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin_user_id: int | None = None,
) -> dict:
    query = rated_tasks_query(db)
    query = _apply_time_filters(query, since, until)
    if rating is not None:
        query = query.filter(Task.user_rating == rating)
    if task_type and task_type.strip():
        query = query.filter(Task.task_type == task_type.strip())
    if model_id and model_id.strip():
        mid = model_id.strip()
        query = query.filter(
            (Task.model_id == mid)
            | ((Task.model_id.is_(None)) & (Task.video_backend == mid))
        )
    query = query.order_by(Task.rated_at.desc().nullslast(), Task.created_at.desc())
    rows = query.all()
    rows = [t for t in rows if not is_mock_task(t)]
    total = len(rows)
    rows = rows[offset : offset + limit]
    return {
        "items": [serialize_feedback_record(t, admin_user_id) for t in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _aggregate_for_analysis(rows: list[Task]) -> dict:
    by_model: dict[str, dict] = defaultdict(
        lambda: {"satisfied": 0, "unsatisfied": 0, "tags": Counter(), "samples": []}
    )
    for task in rows:
        if is_mock_task(task):
            continue
        if task.user_rating == 0 and task.status != "completed":
            continue
        mid = effective_model_id(task)
        bucket = by_model[mid]
        if task.user_rating == 1:
            bucket["satisfied"] += 1
        else:
            bucket["unsatisfied"] += 1
            for tag in parse_rating_tags(task.rating_tags):
                bucket["tags"][tag] += 1
            if len(bucket["samples"]) < 5:
                bucket["samples"].append(
                    {
                        "task_id": task.id,
                        "task_type": task.task_type,
                        "original_input": (task.original_input or "")[:400],
                        "compiled_prompt": (task.compiled_prompt or "")[:400],
                        "rating_tags": parse_rating_tags(task.rating_tags),
                        "rating_comment": (task.rating_comment or "")[:200],
                        "generation_params": parse_generation_params(task.generation_params),
                    }
                )
    payload = {}
    for mid, data in by_model.items():
        payload[mid] = {
            "satisfied": data["satisfied"],
            "unsatisfied": data["unsatisfied"],
            "top_tags": dict(data["tags"].most_common(8)),
            "unsatisfied_samples": data["samples"],
        }
    return payload


def _extract_analysis_json(text: str) -> dict | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return None
    return None


def build_feedback_trends(db: Session, *, days: int = 30) -> dict:
    days = max(1, min(days, 90))
    end = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=0)
    start = (end - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    rows = (
        rated_tasks_query(db)
        .filter(Task.rated_at.isnot(None))
        .filter(Task.rated_at >= start)
        .filter(Task.rated_at <= end)
        .all()
    )

    daily: dict[str, dict] = {}
    for i in range(days):
        day = (start + timedelta(days=i)).date().isoformat()
        daily[day] = {"date": day, "total": 0, "satisfied": 0, "top_tag": None, "_tags": Counter()}

    for task in rows:
        if not task.rated_at:
            continue
        day = task.rated_at.astimezone(timezone.utc).date().isoformat()
        if day not in daily:
            continue
        daily[day]["total"] += 1
        if task.user_rating == 1:
            daily[day]["satisfied"] += 1
        if task.user_rating == 0:
            for tag in parse_rating_tags(task.rating_tags):
                daily[day]["_tags"][tag] += 1

    series = []
    for day in sorted(daily.keys()):
        entry = daily[day]
        total = entry["total"]
        rate = round(entry["satisfied"] / total, 2) if total else 0.0
        top_tag = None
        if entry["_tags"]:
            tag, _ = entry["_tags"].most_common(1)[0]
            top_tag = tag
        series.append(
            {
                "date": day,
                "total": total,
                "satisfied_rate": rate,
                "top_tag": top_tag,
            }
        )
    return {"days": days, "series": series}


def list_feedback_analyses(db: Session, *, limit: int = 20) -> dict:
    limit = max(1, min(limit, 50))
    rows = (
        db.query(FeedbackAnalysisRun)
        .order_by(FeedbackAnalysisRun.created_at.desc())
        .limit(limit)
        .all()
    )
    items = []
    for row in rows:
        parsed = None
        if row.analysis_json:
            try:
                parsed = json.loads(row.analysis_json)
            except json.JSONDecodeError:
                parsed = None
        items.append(
            {
                "id": row.id,
                "created_at": to_utc_iso(row.created_at),
                "record_count": row.record_count,
                "vision_count": row.vision_count,
                "analysis": row.analysis_text,
                "analysis_json": parsed,
            }
        )
    return {"items": items}


def query_feedback_for_analysis(
    db: Session,
    *,
    rating: int | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 200,
) -> list[Task]:
    query = rated_tasks_query(db).filter(Task.status == "completed")
    query = _apply_time_filters(query, since, until)
    if rating is not None:
        query = query.filter(Task.user_rating == rating)
    if task_type and task_type.strip():
        query = query.filter(Task.task_type == task_type.strip())
    if model_id and model_id.strip():
        mid = model_id.strip()
        query = query.filter(
            (Task.model_id == mid)
            | ((Task.model_id.is_(None)) & (Task.video_backend == mid))
        )
    rows = (
        query.order_by(Task.rated_at.desc().nullslast(), Task.created_at.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [t for t in rows if not is_mock_task(t)]


async def analyze_feedback_records(
    db: Session,
    admin_user_id: int,
    *,
    rating: int | None = None,
    model_id: str | None = None,
    task_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    rows = query_feedback_for_analysis(
        db,
        rating=rating,
        model_id=model_id,
        task_type=task_type,
        since=since,
        until=until,
    )
    if len(rows) < 10:
        raise HTTPException(status_code=400, detail="数据不足，至少需要10条评价")

    aggregated = _aggregate_for_analysis(rows)
    aggregated_json = json.dumps(aggregated, ensure_ascii=False, indent=2)
    user_text = ANALYZE_USER_PROMPT_TEMPLATE.format(aggregated=aggregated_json)

    vision_blocks, vision_meta = await build_vision_samples(rows, admin_user_id)
    vision_count = sum(1 for item in vision_meta if item.get("vision") == "image")

    try:
        analysis, _finish, llm_model_id = await call_feedback_analysis_llm(
            db,
            ANALYZE_SYSTEM_PROMPT,
            user_text,
            vision_blocks if vision_blocks else None,
            max_tokens=8192,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM 分析失败: {exc}") from exc

    if not analysis:
        raise HTTPException(status_code=502, detail="LLM 返回空内容")

    analysis_json = _extract_analysis_json(analysis)
    run = FeedbackAnalysisRun(
        id=str(uuid.uuid4()),
        record_count=len(rows),
        vision_count=vision_count,
        analysis_text=analysis,
        analysis_json=json.dumps(analysis_json, ensure_ascii=False) if analysis_json else None,
        created_by=admin_user_id,
    )
    db.add(run)
    db.commit()

    return {
        "analysis": analysis,
        "analysis_json": analysis_json,
        "vision_count": vision_count,
        "vision_meta": vision_meta,
        "llm_model_id": llm_model_id,
        "run_id": run.id,
    }
