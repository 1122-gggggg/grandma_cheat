"""終端大字報：會場吵雜也能一眼看懂的三態顯示（顏色＋圖示＋分數條）。"""

from __future__ import annotations

from antiscam.contracts import Alert, ScoreResult
from antiscam.guardian.passcode import get_passcode_prompt
from antiscam.guardian.tts_text import (
    normalize_label,
    safe_score,
    to_ta_warning,
    to_zh_detail,
)

# 門檻與 brain.Scorer 對齊（BrainWorker 規格）：分數 >= 0.8 詐騙，>= 0.4 可疑，否則正常
FRAUD_THRESHOLD = 0.8
SUSPECT_THRESHOLD = 0.4

# Alert 等級沿用 contracts 的 info / warning / danger 寫法
_LEVEL_OF = {"fraud": "danger", "suspect": "warning", "safe": "info"}

# 終端顏色（紅＝危險、黃＝可疑、綠＝正常）
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_RESET = "\033[0m"
_COLOR_OF = {"fraud": _RED, "suspect": _YELLOW, "safe": _GREEN}

# 三態圖示與大標題
_ICON_OF = {"fraud": "⚠️", "suspect": "⚡", "safe": "✅"}
_TITLE_OF = {
    "fraud": "阿嬤注意！這通可能是詐騙",
    "suspect": "這通有可疑，先不要匯錢",
    "safe": "這通目前正常",
}

_BAR_WIDTH = 20  # 分數條格數


def _label_of(score: ScoreResult | None, value: float) -> str:
    """有標籤信標籤，沒標籤才用門檻從分數推。"""
    raw = getattr(score, "label", None)
    if raw:
        return normalize_label(raw)
    if value >= FRAUD_THRESHOLD:
        return "fraud"
    if value >= SUSPECT_THRESHOLD:
        return "suspect"
    return "safe"


def _bar(value: float) -> str:
    """20 格分數條：█ 已得分數，░ 未得（全形字，遠看也清楚）。"""
    filled = min(max(int(round(value * _BAR_WIDTH)), 0), _BAR_WIDTH)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


def decide(score: ScoreResult | None) -> Alert:
    """用分數門檻（與 brain 同）轉成 Alert；空輸入回 info，不崩潰。"""
    value = safe_score(getattr(score, "score", 0.0))
    if value >= FRAUD_THRESHOLD:
        kind = "fraud"
    elif value >= SUSPECT_THRESHOLD:
        kind = "suspect"
    else:
        kind = "safe"
    return Alert(
        level=_LEVEL_OF[kind],
        message_zh=to_zh_detail(score),
        message_ta=to_ta_warning(kind),
    )


def render(score: ScoreResult | None) -> str:
    """輸出終端大字報字串（呼叫端 print 即可）；空輸入也回傳 safe 版面。"""
    value = safe_score(getattr(score, "score", 0.0))
    kind = _label_of(score, value)
    color = _COLOR_OF[kind]
    icon = _ICON_OF[kind]
    border = "＝" * 24
    passcode_info = (
        get_passcode_prompt(score) if score is not None else {"triggered": False}
    )
    lines = [
        f"{color}{border}{_RESET}",
        f"{color}{icon}  {_TITLE_OF[kind]}  {icon}{_RESET}",
        f"{color}風險分數：{value:.0%}（{value:.2f}）{_RESET}",
        f"{color}［{_bar(value)}］{_RESET}",
        to_zh_detail(score),
        f"台語：{to_ta_warning(kind)}",
    ]
    if passcode_info.get("triggered") and kind in ("fraud", "suspect"):
        box_border = "★" * 24
        prompt_ta = passcode_info.get("prompt_ta", "")
        prompt_zh = passcode_info.get("prompt_zh", "")
        lines.extend(
            [
                f"{color}{box_border}{_RESET}",
                f"{color}【家庭通關密語防線】{_RESET}",
                f"{color}🗣️  {prompt_ta}{_RESET}",
                f"{color}📋  {prompt_zh}{_RESET}",
                f"{color}{box_border}{_RESET}",
            ]
        )
    lines.append(f"{color}{border}{_RESET}")
    return "\n".join(lines)
