# G30 人物一致性 + LTX2 — 完成状态（2026-07-09）

> 计划已闭环。勿改 `.cursor/plans/g30_pulid_ltx2_*.plan.md`。主交接见 [`HANDOFF.md`](HANDOFF.md) / [`HANDOFF_SERVER.md`](HANDOFF_SERVER.md)。

## 一句话状态

**G30 已完成**：phash 基线、flux-pulid 全栈（GPU 出图 PASS）、ltx2-fp4 API + 结构探针 PASS、pytest 73 passed。

## 验收摘要

| 项 | 状态 |
|----|------|
| Supervisor 6006/7788/8000 | ✅（关机后需手动 `supervisord -c /etc/supervisor/supervisord.conf`） |
| nunchaku + PuLID 节点 | ✅ |
| PuLID GPU 出图 | ✅ `g30_pulid_smoke.json` |
| flux-pulid / ltx2-fp4 结构探针 | ✅ PASS |
| pytest | ✅ 73 passed |
| phash 对照 | ✅ flux-dev 002–003=17 → pulid=8（`g30_phash_compare.json`） |
| facexlib | ✅ 权重在 `models/facexlib/*.pth` 根目录 |

## phash 对照

| 镜对 | flux-dev | flux-pulid |
|------|----------|------------|
| 001-002 | 13 | 14 |
| 002-003 | **17** (drift) | **8** |

参考脸：`/tmp/face_ref.png`（nunchaku 官方测试图）。

*更新：2026-07-09*
