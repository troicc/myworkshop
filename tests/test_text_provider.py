from __future__ import annotations

from app.providers.text import extract_json


def test_extract_json_from_fence() -> None:
    assert extract_json('```json\n{"ok": true}\n```') == {"ok": True}


def test_extract_json_from_surrounding_text() -> None:
    assert extract_json('结果如下： {"count": 3} 完成') == {"count": 3}
