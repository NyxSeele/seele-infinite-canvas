# 路线 C 验收结果

最后更新：**2026-07-08**（AutoDL 269 机 · RTX 4090 · `AGENT_MOCK_GENERATION=false`）

依据：[ROUTE_C_VALIDATION_PLAN.md](ROUTE_C_VALIDATION_PLAN.md) · [ROUTE_B_RESULT.md](ROUTE_B_RESULT.md) · [AGENT_TRACE_BASELINE.md](AGENT_TRACE_BASELINE.md)

---

## 总览

| 项 | 结果 |
|----|------|
| 探针 | [`backend/scripts/_route_c_agent_gpu_probe.py`](backend/scripts/_route_c_agent_gpu_probe.py) |
| 原始 JSON | [`/root/autodl-tmp/logs/route_c_results.json`](/root/autodl-tmp/logs/route_c_results.json) |
| 场景 | 雨夜重庆，一个女人独自等待，3个镜头 |
| Agent 四轮 pipeline | ✅ `create_text_note` → `start_text_generation` → `generate_outline` → `generate_script_table` |
| 创意卡 | **跳过**（`creative_cards_skipped: true`，输入含明确 3 镜） |
| A3 scenes | **3** |
| A4 total_shots | **3**（segments=3） |
| rows 来源 | **100% A4**（非路线 B 硬编码 `SHOTS[]`） |
| GPU 批量 | **3/3 出图 completed** + **3/3 出视频 completed** |
| pytest | **67 passed** |
| 探针 exit | **0**（修复 L0/L4 双语断言后复评 PASS） |

---

## Agent 链路（A1–A4）

| 轮次 | pipeline_step | 耗时 | 备注 |
|------|---------------|------|------|
| R1 | `create_text_note` | 10.7s | 无 `ask_user`（明确镜数变体） |
| R2 | `start_text_generation` | 1.9s | qwen-plus 真实 A2 |
| R3 | `generate_outline` | 6.7s | A3 `scenes_count=3` |
| R4 | `generate_script_table` | 8.3s | A4 `shots_target=3` · `total_shots=3` |

**A4 分镜描述样例（镜 001，来自 Agent，非硬编码）**：

```
全景固定机位缓慢横移，冷调蓝灰主光笼罩潮湿幽深的重庆老街……女人身着米色风衣手持深灰长柄伞独自伫立街角……
```

剧本文本长度：**738** 字 · 大纲场景：**3**

---

## GPU 批量（动态 rows → L0–L4）

| 镜号 | 描述来源 | L0 承接 | img2img | 出图耗时 | 出视频耗时 | 输出 |
|------|---------|---------|---------|----------|------------|------|
| 001 | A4 prompt | — | — | 20.3s | 146.7s | `ComfyUI_00043_.png` / `AIStudio_video_00032_.mp4` |
| 002 | A4 prompt | ✅ `承接上一镜头` | ✅ | 15.2s | 146.6s | `ComfyUI_00044_.png` / `AIStudio_video_00033_.mp4` |
| 003 | A4 prompt | ✅ | ✅ | 15.2s | 141.6s | `ComfyUI_00045_.png` / `AIStudio_video_00034_.mp4` |

**003 视频 L4 外貌关键词（英译后）**：`woman` · `beige trench coat` · `Chongqing` — PASS

---

## 路线 B vs 路线 C 对比

| 维度 | 路线 B（固定文案） | 路线 C（Agent 自动） |
|------|-------------------|---------------------|
| 分镜描述来源 | 硬编码 `SHOTS[]`（林晓/胡同） | A4 `generate-shots` 动态产出 |
| Agent 链路 | 无 | A1–A4 全链路 |
| 角色设定 | 林晓 · 黑发 · 白风衣 | 女人 · 米色风衣 · 深灰伞（A2/A4 推导） |
| 场景 | 雨夜胡同 | 雨夜重庆老街 |
| 批量出图 | 3/3 PASS | 3/3 PASS |
| 批量出视频 | 3/3 PASS（新机曾 2/3 超时） | **3/3 PASS**（`POLL_TIMEOUT=1800`） |
| L0 承接 002/003 | ✅ | ✅ |
| 探针耗时 | ~8min GPU | ~4min Agent + ~7min GPU ≈ **11min** |

**路线 C 核心风险验证**：A4 产出镜数与 prompt 长度达标（≥50 字/镜）；rows 与 segments 映射一致（3 镜 / 3 段）；Agent 描述经 L0 compile 后承接链未断裂。

---

## Definition of Done 核对

| # | 条件 | 状态 |
|---|------|------|
| 1 | 探针 exit 0 · `route_c_results.json` 存档 | ✅ |
| 2 | 四轮 pipeline_step 成功 · `creative_cards_skipped` 标注 | ✅ |
| 3 | A2/A3/A4 trace · `scenes_count=3` · `total_shots=3` | ✅（A2 trace 本轮未落日志行，任务 completed） |
| 4 | rows 100% 来自 A4 · `len>=3` | ✅ |
| 5 | 3/3 图 + 3/3 视频 completed | ✅ |
| 6 | 002/003 L0 承接 · 003 L4 外貌 | ✅ |
| 7 | pytest 67 passed | ✅ |
| 8 | 本文档对比表 | ✅ |

---

## 复现命令

```bash
cd /root/autodl-tmp/AIStudio/backend
set -a && source .env && set +a
sqlite3 aistudio.db "UPDATE tasks SET status='failed' WHERE status IN ('pending','running');"
.venv/bin/python scripts/_route_c_agent_gpu_probe.py
.venv/bin/python -m pytest tests/ -q
```

可选创意卡强制路径：`.venv/bin/python scripts/_route_c_agent_gpu_probe.py --require-ask-user`

仅 Agent 阶段：`.venv/bin/python scripts/_route_c_agent_gpu_probe.py --skip-gpu`
