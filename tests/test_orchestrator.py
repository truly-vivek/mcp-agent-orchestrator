from types import SimpleNamespace

from app.orchestrator import safe_tool_name, serialize_tool_result


def test_safe_tool_name_namespaces_and_normalizes():
    assert safe_tool_name("local tools", "lookup.item") == "local_tools__lookup_item"


def test_safe_tool_name_respects_function_name_limit():
    assert len(safe_tool_name("s" * 50, "t" * 50)) == 64


def test_serialize_tool_result_reads_text_blocks():
    result = SimpleNamespace(content=[
        SimpleNamespace(text="first result"),
        SimpleNamespace(text="second result"),
    ])
    assert serialize_tool_result(result) == "first result\nsecond result"
