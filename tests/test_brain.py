"""大腦測試：不需 Ollama，純關鍵詞即可通過（斷網 demo 也能跑）。"""

from pathlib import Path

from antiscam.brain.patterns import load_patterns
from antiscam.brain.scorer import Scorer


def test_fake_police_sentence_is_fraud() -> None:
    """假檢警句（地檢署＋監管帳戶）必須 >= 0.8 且標為 fraud。"""
    scorer = Scorer()
    text: str = "這裡是地檢署，你的帳戶涉及洗錢，必須把錢轉到監管帳戶接受調查。"
    result = scorer.score(text)
    assert 0.0 <= result.score <= 1.0
    assert result.score >= 0.8
    assert result.label == "fraud"
    assert len(result.matched) > 0


def test_normal_greeting_is_safe() -> None:
    """正常句（孫子問吃飽沒）必須 < 0.4 且標為 safe。"""
    scorer = Scorer()
    text: str = "阿嬤，你吃飽沒？我是你孫子啦，打電話來問候一下。"
    result = scorer.score(text)
    assert 0.0 <= result.score <= 1.0
    assert result.score < 0.4
    assert result.label == "safe"


def test_empty_string_is_safe() -> None:
    """空字串不崩潰，直接回 safe。"""
    scorer = Scorer()
    result = scorer.score("")
    assert 0.0 <= result.score <= 1.0
    assert result.label == "safe"
    assert result.matched == []


def test_load_patterns_missing_file_returns_empty(tmp_path: Path) -> None:
    """樣板檔缺檔時回空串列，不丟例外。"""
    assert load_patterns(str(tmp_path / "not_exist.json")) == []
