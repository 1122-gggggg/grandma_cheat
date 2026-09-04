"""台語警告文字組裝（純字串，不讀音檔、不呼叫 TTS 引擎）。"""

from __future__ import annotations

from antiscam.contracts import ScoreResult

# 三態標籤的同義寫法：brain 回 "suspicious"、demo 層可能寫 "suspect"，全部吃下
_FRAUD_LABELS = frozenset({"fraud", "danger", "high", "詐騙"})
_SUSPECT_LABELS = frozenset(
    {"suspect", "suspicious", "warn", "warning", "medium", "可疑"}
)

# 中文判定的顯示文字
_LABEL_ZH = {"fraud": "高風險（疑似詐騙）", "suspect": "可疑", "safe": "正常"}


def normalize_label(label: object) -> str:
    """把各種標籤寫法正規化成 "fraud" / "suspect" / "safe"。"""
    text = str(label or "").strip().lower()
    if text in _FRAUD_LABELS:
        return "fraud"
    if text in _SUSPECT_LABELS:
        return "suspect"
    return "safe"


def to_ta_warning(label: str | None) -> str:
    """依三態標籤回傳一句唸給阿嬤聽的台語警告（空輸入回正常句，不崩潰）。"""
    kind = normalize_label(label)
    if kind == "fraud":
        return "阿嬤，這是騙人的，緊掛斷！"
    if kind == "suspect":
        return "阿嬤，這通有可疑，先毋通匯錢。"
    return "這通正常。"


def safe_score(value: object) -> float:
    """把分數夾到 0~1；髒輸入（None、字串、NaN）一律當 0.0，不崩潰。"""
    try:
        number = float(value if value is not None else 0.0)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN 不等於自己
        return 0.0
    return min(max(number, 0.0), 1.0)


def to_zh_detail(result: ScoreResult | None) -> str:
    """把評分結果翻成一句中文明細（給家人／評審看，空輸入回預設句）。"""
    if result is None:
        return "尚無分析結果。"
    score = safe_score(getattr(result, "score", 0.0))
    kind = normalize_label(getattr(result, "label", "safe"))
    matched = getattr(result, "matched", None) or []
    reasons = getattr(result, "reasons", None) or []
    hit = "、".join(str(w) for w in matched) if matched else "無"
    why = "；".join(str(r) for r in reasons) if reasons else "無明顯特徵"
    return (
        f"風險分數 {score:.0%}（{score:.2f}），判定：{_LABEL_ZH[kind]}；"
        f"命中關鍵詞：{hit}；理由：{why}。"
    )
