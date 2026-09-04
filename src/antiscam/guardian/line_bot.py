"""LINE 真推播：有 token 才打 Push API，無 token／斷網自動降級寫本地 log。

契約：
- ``LineBot().push(alert)`` 讀環境變數 ``LINE_CHANNEL_TOKEN``／``LINE_TARGET_ID``。
- 有 token 才打 ``api.line.me/v2/bot/message/push``（urllib 標準庫，timeout=5s，單次呼叫不重試）。
- 無 token、無 target、或連線失敗，一律回落調 ``Notifier().notify`` 寫本地 log，
  回傳 ``{"mode": "mock", "logged": ...}``，demo 可直接投影同一行。
- token 絕不寫死在程式碼，只從環境變數讀取；本模組絕不修改 notifier.py。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from antiscam.contracts import Alert
from antiscam.guardian.notifier import Notifier

# LINE Messaging API Push endpoint（固定值，非機密）。
PUSH_URL = "https://api.line.me/v2/bot/message/push"

# 單次推送逾時（秒）：決賽現場網路不穩也要快速失敗、立刻降級，不卡 demo。
_PUSH_TIMEOUT = 5


def _text_of(alert: Alert | None) -> str:
    """把 Alert 組成一行 LINE 文字；空告警給預設字串，避免送出空訊息被 API 退件。"""
    level: str = str(getattr(alert, "level", None) or "info")
    zh: str = str(getattr(alert, "message_zh", None) or "")
    ta: str = str(getattr(alert, "message_ta", None) or "")
    text = f"【阿嬤守門員・{level}】{zh}"
    if ta and ta not in text:
        text += f"\n{ta}"
    text = text.strip()
    if not zh and not ta:
        text = f"【阿嬤守門員・{level}】（測試推播）"
    return text


class LineBot:
    """LINE 推播器：有 token 走真推播，否則靜默降級為本地 log。"""

    def __init__(self, log_path: str | Path | None = None) -> None:
        """指定降級時 Notifier 的 log 檔位置；預設 ``runs/line_mock.log``。

        只收 log 路徑，不收 token：token 一律在 ``push()`` 當下讀環境變數，
        避免程序啟動後才 export 卻讀不到舊值。
        """
        self.log_path = Path(log_path) if log_path is not None else None

    def _fallback(
        self, alert: Alert | None, reason: str, error: str = ""
    ) -> dict[str, Any]:
        """回落寫本地 log，回傳 mock 結果（demo 投影用同一行）。"""
        notifier = (
            Notifier(log_path=self.log_path)
            if self.log_path is not None
            else Notifier()
        )
        logged: dict[str, Any] = notifier.notify(alert)
        result: dict[str, Any] = {"mode": "mock", "reason": reason, "logged": logged}
        if error:
            result["error"] = error
        return result

    def push(self, alert: Alert | None) -> dict[str, Any]:
        """推送一則告警；無 token 或連線失敗自動降級寫本地 log。

        無 token 時零網路呼叫，直接回落；有 token 時單次 POST，失敗不重試、
        立刻降級，避免重試風暴卡住 demo。
        """
        token: str = (os.getenv("LINE_CHANNEL_TOKEN") or "").strip()
        target: str = (os.getenv("LINE_TARGET_ID") or "").strip()
        if not token:
            return self._fallback(alert, reason="no_token")
        if not target:
            return self._fallback(alert, reason="no_target")

        payload: dict[str, Any] = {
            "to": target,
            "messages": [{"type": "text", "text": _text_of(alert)}],
        }
        body: bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            PUSH_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            # 單次呼叫，不重試：任何例外都直接降級。
            with urllib.request.urlopen(req, timeout=_PUSH_TIMEOUT) as resp:
                raw: str = resp.read().decode("utf-8", errors="replace")
                status: int = int(getattr(resp, "status", 200) or 200)
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            return self._fallback(
                alert, reason="network_error", error=f"{type(exc).__name__}: {exc}"
            )
        try:
            parsed: Any = json.loads(raw) if raw.strip() else {}
        except ValueError:
            parsed = {"raw": raw}
        return {"mode": "live", "status": status, "target": target, "response": parsed}
