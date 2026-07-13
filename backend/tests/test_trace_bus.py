import asyncio

from trace_bus import get_trace_queue, push_trace


def test_push_trace_accepts_string_layer():
    queue = get_trace_queue()
    while not queue.empty():
        queue.get_nowait()

    asyncio.run(push_trace("A1", "AGENT_INPUT", {"messages_count": 3}))
    item = asyncio.run(asyncio.wait_for(queue.get(), timeout=1.0))
    assert item["layer"] == "A1"
    assert item["tag"] == "AGENT_INPUT"
    assert item["data"]["messages_count"] == 3


def test_push_trace_accepts_int_layer():
    queue = get_trace_queue()
    while not queue.empty():
        queue.get_nowait()

    asyncio.run(push_trace(0, "COMPILED", {"positive_len": 10}))
    item = asyncio.run(asyncio.wait_for(queue.get(), timeout=1.0))
    assert item["layer"] == 0
    assert item["tag"] == "COMPILED"
