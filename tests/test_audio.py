"""音訊測試：空音/不存在檔不崩、Segment 欄位型別。

注意：依任務約定不執行 pytest，這裡只提供測試函式供主流程驗收。
"""

from __future__ import annotations

import numpy as np

from antiscam.audio.transcriber import Transcriber
from antiscam.audio.vad import split_window
from antiscam.contracts import Segment


def test_split_window_empty_returns_empty() -> None:
    """空陣列應回空 list 且不拋錯。"""
    assert split_window(np.array([], dtype=np.float32), 16000) == []


def test_split_window_silence_skipped() -> None:
    """全靜音 10 秒應全部跳過，回空 list。"""
    silent: np.ndarray = np.zeros(16000 * 10, dtype=np.float32)
    assert split_window(silent, 16000) == []


def test_split_window_none_no_crash() -> None:
    """None 輸入應回空 list 且不拋錯。"""
    assert split_window(None, 16000) == []  # type: ignore[arg-type]


def test_split_window_tone_kept() -> None:
    """有聲音 10 秒應保留至少一個窗口，且區間合法。"""
    sr: int = 16000
    t: np.ndarray = np.arange(sr * 10, dtype=np.float32) / sr
    tone: np.ndarray = (0.5 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    wins: list[tuple[int, int]] = split_window(tone, sr)
    assert len(wins) >= 1
    for start, end in wins:
        assert isinstance(start, int) and isinstance(end, int)
        assert 0 <= start < end <= sr * 10


def test_transcribe_missing_file_no_crash() -> None:
    """不存在的 wav 應回單一空 Segment 且不拋錯。"""
    tr: Transcriber = Transcriber()
    out: list[Segment] = tr.transcribe("/nonexistent/no_such_file.wav")
    assert isinstance(out, list) and len(out) == 1
    assert out[0].text == ""


def test_transcribe_empty_path_no_crash() -> None:
    """空路徑應回單一空 Segment 且不拋錯。"""
    tr: Transcriber = Transcriber()
    out: list[Segment] = tr.transcribe("")
    assert isinstance(out, list) and len(out) == 1
    assert out[0].text == ""


def test_segment_field_types() -> None:
    """Segment 欄位型別：text/str、start/float、end/float、lang/str。"""
    tr: Transcriber = Transcriber()
    out: list[Segment] = tr.transcribe("/nonexistent/no_such_file.wav")
    seg: Segment = out[0]
    assert isinstance(seg.text, str)
    assert isinstance(seg.start, float)
    assert isinstance(seg.end, float)
    assert isinstance(seg.lang, str)


def test_transcriber_lazy_no_model_on_init() -> None:
    """建構時不載模型（import/建構不觸發下載），_model 保持 None。"""
    tr: Transcriber = Transcriber()
    assert tr._model is None
