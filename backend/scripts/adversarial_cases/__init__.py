"""对抗性 Prompt 测试用例集合（按类别分文件）。"""

from adversarial_cases.cast_scene_boundary import CASES as CAST_SCENE_CASES
from adversarial_cases.contradiction_undo import CASES as CONTRADICTION_UNDO_CASES
from adversarial_cases.multi_chain_reference import CASES as MULTI_CHAIN_CASES
from adversarial_cases.short_commands import CASES as SHORT_COMMAND_CASES
from adversarial_cases.skip_step import CASES as SKIP_STEP_CASES
from adversarial_cases.template_handoff import CASES as TEMPLATE_HANDOFF_CASES

ALL_CASES: list[dict] = [
    *SHORT_COMMAND_CASES,
    *CAST_SCENE_CASES,
    *MULTI_CHAIN_CASES,
    *CONTRADICTION_UNDO_CASES,
    *SKIP_STEP_CASES,
    *TEMPLATE_HANDOFF_CASES,
]

CASES_BY_CATEGORY: dict[str, list[dict]] = {
    "short_commands": SHORT_COMMAND_CASES,
    "cast_scene_boundary": CAST_SCENE_CASES,
    "multi_chain_reference": MULTI_CHAIN_CASES,
    "contradiction_undo": CONTRADICTION_UNDO_CASES,
    "skip_step": SKIP_STEP_CASES,
    "template_handoff": TEMPLATE_HANDOFF_CASES,
}
