"""Line 模擬通知：只寫本地 log，絕不打真實 Line API。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from antiscam.contracts import Alert

# 預設 log 位置（相對於執行時的工作目錄，也就是專案根目錄）
DEFAULT_LOG_PATH = Path("runs/line_mock.log")


class Notifier:
    """Alert 的本機替身：notify() 寫一行 JSON 到 log 檔並回傳該 dict。"""

    def __init__(self, log_path: str | Path | None = None) -> None:
        """指定 log 檔位置；預設 runs/line_mock.log（測試可傳 tmp 路徑隔離）。"""
        self.log_path = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH

    def notify(self, alert: Alert | None) -> dict[str, Any]:
        """寫檔並回傳該筆紀錄；alert 為空也記一筆 info，不崩潰。"""
        record: dict[str, Any] = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "level": str(getattr(alert, "level", None) or "info"),
            "message_zh": str(getattr(alert, "message_zh", None) or ""),
            "message_ta": str(getattr(alert, "message_ta", None) or ""),
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
