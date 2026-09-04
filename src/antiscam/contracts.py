"""共用契約：全隊照此介面寫，不互相等待。

本模組只放資料結構，不放模型邏輯：
- Segment：語音轉文字的一段結果（含時間戳與語言）。
- ScoreResult：詐騙評分的結果（0~1 分數、標籤、命中關鍵詞、理由）。
- Alert：要通知阿嬤的告警（等級 + 中文/台語訊息）。

傳輸時用 to_dict() 轉成 dict（寫 log / demo 層 10 秒滑動窗口用）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Segment:
    """語音辨識的一段文字。"""

    text: str  # 辨識出的文字內容
    start: float  # 開始時間（秒）
    end: float  # 結束時間（秒）
    lang: str  # 語言標籤，如 "zh"（華語）、"ta"（台語）、"mixed"（混雜）

    def to_dict(self) -> dict[str, object]:
        """轉成 dict，方便寫 log 或傳給 demo 層。"""
        return asdict(self)


@dataclass(frozen=True)
class ScoreResult:
    """詐騙評分結果，分數介於 0~1，越高越可疑。"""

    score: float  # 0.0（安全）~ 1.0（高度可疑）
    label: str  # 判斷標籤，如 "safe" / "suspicious" / "fraud"
    matched: list[str] = field(default_factory=list)  # 命中的關鍵詞
    reasons: list[str] = field(default_factory=list)  # 判斷理由（給人看的說明）

    def to_dict(self) -> dict[str, object]:
        """轉成 dict，方便寫 log 或傳給 demo 層。"""
        return asdict(self)


@dataclass(frozen=True)
class Alert:
    """要通知阿嬤的告警訊息。"""

    level: str  # 等級，如 "info" / "warning" / "danger"
    message_zh: str  # 中文訊息（給家人/評審看）
    message_ta: str  # 台語訊息（唸給阿嬤聽，台羅或漢字皆可）

    def to_dict(self) -> dict[str, object]:
        """轉成 dict，方便寫 log（Notifier.notify 只寫 local log，不打真網路）。"""
        return asdict(self)
