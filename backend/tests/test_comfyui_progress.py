"""Multi-stage ComfyUI progress aggregation tests."""
from services import comfyui_progress as prog
from comfyui.client import count_workflow_sampler_stages


def setup_function():
    prog.clear_progress("p1")


def test_count_workflow_sampler_stages():
    assert count_workflow_sampler_stages({
        "a": {"class_type": "KSamplerAdvanced"},
        "b": {"class_type": "KSamplerAdvanced"},
        "c": {"class_type": "VAEDecode"},
    }) == 2
    assert count_workflow_sampler_stages({
        "113": {"class_type": "SamplerCustomAdvanced"},
        "119": {"class_type": "SamplerCustomAdvanced"},
    }) == 2
    assert count_workflow_sampler_stages({
        "71": {"class_type": "KSampler"},
    }) == 1
    assert count_workflow_sampler_stages({}) == 1


def test_single_stage_maps_to_running_cap():
    prog.set_expected_stages("p1", 1)
    prog.record_progress("p1", 10, 20, node="sampler")
    assert prog.get_progress("p1")["progress"] == 48  # 0.5 * 95
    prog.record_progress("p1", 20, 20, node="sampler")
    assert prog.get_progress("p1")["progress"] == 95


def test_dual_stage_wan_no_reset_to_zero():
    prog.set_expected_stages("p1", 2)
    prog.record_progress("p1", 1, 2, node="w22i_sample_h")
    p1 = prog.get_progress("p1")["progress"]
    assert 20 <= p1 <= 30  # ~25%
    prog.record_progress("p1", 2, 2, node="w22i_sample_h")
    p2 = prog.get_progress("p1")["progress"]
    assert 45 <= p2 <= 50  # ~47.5%

    prog.record_progress("p1", 1, 2, node="w22i_sample_l")
    p3 = prog.get_progress("p1")["progress"]
    assert p3 >= p2
    assert 70 <= p3 <= 75  # ~71%
    prog.record_progress("p1", 2, 2, node="w22i_sample_l")
    p4 = prog.get_progress("p1")["progress"]
    assert p4 >= p3
    assert p4 == 95


def test_ltx2_dual_sampler_custom_advanced():
    prog.set_expected_stages("p1", 2)
    prog.record_progress("p1", 2, 2, node="113")
    after_first = prog.get_progress("p1")["progress"]
    prog.record_progress("p1", 1, 2, node="119")
    assert prog.get_progress("p1")["progress"] >= after_first


def test_progress_is_monotonic_against_out_of_order():
    prog.set_expected_stages("p1", 2)
    prog.record_progress("p1", 2, 2, node="w22i_sample_h")
    high = prog.get_progress("p1")["progress"]
    prog.record_progress("p1", 1, 2, node="w22i_sample_h")
    assert prog.get_progress("p1")["progress"] == high
