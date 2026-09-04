"""即時鏈路測試：滑動拼接、離線播音降級、麥克風缺件指引。

注意：依任務約定不執行 pytest，這裡只提供測試函式供主流程驗收。
"""

from __future__ import annotations

import sys
from typing import Iterator

import pytest

from antiscam.audio.stream import collect_window, iter_mic_segments
from antiscam.contracts import Segment
from antiscam.guardian.player import speak_ta


def _seg(text: str, start: float, end: float) -> Segment:
    """建一段測試用 Segment（台語／華語混雜皆可）。"""
    return Segment(text=text, start=float(start), end=float(end), lang="ta")


def test_collect_window_joins_and_caps_tail() -> None:
    """拼接多段文字且只留尾端 n_chars 字（10 秒滑動語意）。"""
    segs: list[Segment] = [
        _seg("阿嬤", 0.0, 1.0),
        _seg("，這是騙人的，", 1.0, 3.0),
        _seg("緊掛斷！", 3.0, 4.0),
    ]
    gen: Iterator[Segment] = iter(segs)
    assert collect_window(gen, n_chars=150) == "阿嬤，這是騙人的，緊掛斷！"

    long_segs: list[Segment] = [_seg("騙", float(i), float(i + 1)) for i in range(200)]
    out: str = collect_window(iter(long_segs), n_chars=150)
    assert len(out) == 150
    assert out == "騙" * 150

    assert collect_window(iter([]), n_chars=150) == ""


def test_speak_ta_no_crash_without_soundcard() -> None:
    """無音效卡／缺 pyttsx3 時不拋錯，回 played=False＋reason。"""
    result: dict[str, object] = speak_ta("阿嬤，這是騙人的，緊掛斷！")
    assert isinstance(result, dict)
    assert "played" in result
    assert isinstance(result["played"], bool)
    if result["played"] is False:
        assert "reason" in result
        assert isinstance(result["reason"], str)
        assert len(str(result["reason"])) > 0

    empty: dict[str, object] = speak_ta("")
    assert isinstance(empty, dict)
    assert empty.get("played") is False


def test_iter_mic_missing_backend_message_has_checklist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺 sounddevice 時拋 RuntimeError，訊息含檢查字（不靜默假跑）。"""
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    msg: str = ""
    try:
        gen: Iterator[Segment] = iter_mic_segments()
        try:
            next(gen)
        except RuntimeError as exc_inner:
            msg = str(exc_inner)
        else:
            raise AssertionError("缺 sounddevice 時應拋 RuntimeError，不可靜默假跑。")
    except RuntimeError as exc:
        if not msg:
            msg = str(exc)
    assert "sounddevice" in msg
    assert "麥克風" in msg
    assert "檢查" in msg
    assert ("備份" in msg) or ("fraud" in msg)
