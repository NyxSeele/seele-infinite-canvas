"""GPU pool capability / image-vs-video routing."""

from __future__ import annotations

import pytest

from services.gpu_pool import (
    CAP_IMAGE,
    CAP_VIDEO,
    GPUNode,
    GPUPool,
    default_node_capabilities,
    parse_comfyui_node_spec,
)


def test_parse_node_vram_and_caps():
    url, vram, caps = parse_comfyui_node_spec(
        "https://u1066791-90fc-c93a7df9.westb.seetacloud.com:8443|80"
    )
    assert url.endswith(":8443")
    assert vram == 80
    assert caps == frozenset({CAP_VIDEO})

    url2, vram2, caps2 = parse_comfyui_node_spec("http://127.0.0.1:8000")
    assert vram2 == 32
    assert CAP_IMAGE in caps2 and CAP_VIDEO in caps2

    _, _, caps3 = parse_comfyui_node_spec(
        "https://remote.example:8443|80|video"
    )
    assert caps3 == frozenset({CAP_VIDEO})

    _, _, caps4 = parse_comfyui_node_spec(
        "http://127.0.0.1:8000|32|image+video"
    )
    assert caps4 == frozenset({CAP_IMAGE, CAP_VIDEO})


def test_nodes_env_comma_not_split_by_caps():
    """capability 用 + 连接，避免与 COMFYUI_NODES 逗号分隔冲突。"""
    import os

    from services.gpu_pool import reset_gpu_pool_for_tests

    os.environ["COMFYUI_NODES"] = (
        "http://127.0.0.1:8000|32|image+video,"
        "https://h800.example:8443|80|video"
    )
    pool = reset_gpu_pool_for_tests()
    assert len(pool.nodes) == 2
    assert pool.nodes[0].capabilities == frozenset({CAP_IMAGE, CAP_VIDEO})
    assert pool.nodes[1].capabilities == frozenset({CAP_VIDEO})


def test_default_remote_fat_gpu_is_video_only():
    assert default_node_capabilities("https://h800.example:8443", 80) == frozenset(
        {CAP_VIDEO}
    )
    assert CAP_IMAGE in default_node_capabilities("http://127.0.0.1:8000", 32)


def test_image_stays_on_local_when_h800_free():
    """本机忙于视频时，生图仍不得落到仅视频的 H800。"""
    pool = GPUPool(
        nodes=[
            GPUNode(
                "gpu-0",
                "http://127.0.0.1:8000",
                32,
                busy=True,
                capabilities=frozenset({CAP_IMAGE, CAP_VIDEO}),
            ),
            GPUNode(
                "gpu-1",
                "https://h800.example:8443",
                80,
                busy=False,
                capabilities=frozenset({CAP_VIDEO}),
            ),
        ]
    )
    node = pool.get_available_node(
        required_vram=16, prefer_short=True, capability=CAP_IMAGE
    )
    assert node.comfyui_url == "http://127.0.0.1:8000"


def test_video_high_vram_still_prefers_h800():
    pool = GPUPool(
        nodes=[
            GPUNode(
                "gpu-0",
                "http://127.0.0.1:8000",
                32,
                capabilities=frozenset({CAP_IMAGE, CAP_VIDEO}),
            ),
            GPUNode(
                "gpu-1",
                "https://h800.example:8443",
                80,
                capabilities=frozenset({CAP_VIDEO}),
            ),
        ]
    )
    node = pool.get_available_node(required_vram=40, capability=CAP_VIDEO)
    assert node.comfyui_url.endswith(":8443")


def test_image_capability_missing_raises():
    pool = GPUPool(
        nodes=[
            GPUNode(
                "gpu-1",
                "https://h800.example:8443",
                80,
                capabilities=frozenset({CAP_VIDEO}),
            ),
        ]
    )
    with pytest.raises(RuntimeError, match="capability"):
        pool.get_available_node(required_vram=16, capability=CAP_IMAGE)
