"""家庭通關密語反向驗證機制：長輩反向查證假親友/AI變聲詐騙。

當偵測到假親友詐騙特徵（如 family-* 話術）且風險達到可疑或詐騙等級時，
系統自動提供「通關密語提示」，引導長輩詢問只有真正家人知曉的日常問題（如寵物名字、兒時暱稱），
有效破解 AI 擬真仿聲與視訊深偽（Deepfake）詐騙。
"""

from __future__ import annotations

from typing import Any

from antiscam.contracts import ScoreResult
from antiscam.guardian.tts_text import normalize_label, safe_score

_SUSPECT_OR_FRAUD_LABELS = frozenset(
    {
        "suspect",
        "fraud",
        "suspicious",
        "danger",
        "warning",
        "high",
        "medium",
        "可疑",
        "詐騙",
    }
)


def _is_family_feature(matched_item: str) -> bool:
    """檢查命中關鍵詞是否包含 family- 開頭或親友特徵。"""
    text = str(matched_item or "").strip().lower()
    return text.startswith("family-") or "family" in text or "親友" in matched_item


def get_passcode_prompt(
    score: ScoreResult,
    question: str = "咱家的狗叫啥名？",
) -> dict[str, Any]:
    """檢查是否觸發家庭通關密語反向驗證。

    若 matched 中包含 `family-` 開頭或親友特徵；若符合且為 suspect/fraud，
    回傳::

        {
            "triggered": True,
            "question": question,
            "prompt_ta": f"阿嬤莫慌！先問伊通關密語：『{question}』",
            "prompt_zh": f"防詐密語提示：請長輩詢問對方「{question}」反向驗證身份",
        }

    否則回傳::

        {"triggered": False}

    :param score: 詐騙評分結果 (ScoreResult)
    :param question: 家庭預設的反向驗證通關密語，預設為「咱家的狗叫啥名？」
    :return: 包含 triggered 及密語字串的字典
    """
    if score is None:
        return {"triggered": False}

    matched: list[str] = getattr(score, "matched", []) or []
    has_family = any(_is_family_feature(m) for m in matched)

    # 保底：若 matched 欄位沒有但理由中載明假親友樣板，亦視為符合親友特徵
    if not has_family:
        reasons: list[str] = getattr(score, "reasons", []) or []
        for r in reasons:
            if "假親友" in r or "family-" in r.lower():
                has_family = True
                break

    if not has_family:
        return {"triggered": False}

    # 判斷是否為 suspect 或 fraud
    raw_label = getattr(score, "label", None)
    normalized = normalize_label(raw_label) if raw_label else ""
    value = safe_score(getattr(score, "score", 0.0))

    is_suspect_or_fraud = (
        normalized in ("suspect", "fraud")
        or str(raw_label).strip().lower() in _SUSPECT_OR_FRAUD_LABELS
        or value >= 0.4
    )

    # 若標籤明確為 safe 且分數小於可疑門檻，則不觸發
    if normalized == "safe" and value < 0.4:
        return {"triggered": False}

    if not is_suspect_or_fraud:
        return {"triggered": False}

    return {
        "triggered": True,
        "question": question,
        "prompt_ta": f"阿嬤莫慌！先問伊通關密語：『{question}』",
        "prompt_zh": f"防詐密語提示：請長輩詢問對方「{question}」反向驗證身份",
    }
