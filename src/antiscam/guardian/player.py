"""台語播音：pyttsx3 離線播優先，缺件不拋錯；預錄 wav 佔位介面。

設計說明（給跨領域隊友）：
- ``speak_ta`` 優先用 pyttsx3 在本機離線播台語警語（斷網也能唸）；
  缺套件、無音效卡、播音失敗一律回 ``{played: False, reason: ...}``，不拋錯，
  上層照常顯示文字大字報，``fraud demo`` 不中斷。
- ``write_wav_placeholder`` 留介面給決賽前灌預錄台語 wav：
  有預錄檔就複製就位，沒有就先寫靜音 wav 佔位；全標準庫，無新硬依賴。
- 本檔只用標準庫＋可選依賴 pyttsx3，不加新硬依賴進 pyproject。
"""

from __future__ import annotations

import shutil
import wave
from pathlib import Path
from typing import Any


def speak_ta(
    text: str,
    *,
    rate: int | None = None,
    volume: float | None = None,
) -> dict[str, object]:
    """用離線引擎播出台語警語；播不了就回報原因，不拋錯。

    Args:
        text: 要播的台語文字（例如「阿嬤，這是騙人的，緊掛斷！」）。
        rate: 語速（pyttsx3 ``rate``），``None`` 用系統預設。
        volume: 音量 0.0~1.0（pyttsx3 ``volume``），``None`` 用系統預設。

    Returns:
        成功時 ``{played: True, engine: 'pyttsx3', text: ...}``；
        失敗時 ``{played: False, reason: ..., text: ...}``（缺件／無音效卡皆走此路）。
        本函式不拋錯（鍵盤中斷除外），無播音時上層請照常顯示文字大字報。
    """
    try:
        content: str = str(text or "").strip()
    except Exception:
        content = ""
    if not content:
        return {
            "played": False,
            "reason": "文字為空，無需播音；不影響 fraud demo 文字大字報。",
            "text": "",
        }
    try:
        import pyttsx3  # 可選依賴：缺件走降級回報，不拋錯
    except Exception as exc:
        return {
            "played": False,
            "reason": (
                f"未安裝離線語音引擎 pyttsx3（{exc}）："
                "pip install pyttsx3 後再試；"
                "目前無播音但不影響 fraud demo 文字大字報。"
            ),
            "engine": "pyttsx3",
            "text": content,
        }
    try:
        engine: Any = pyttsx3.init()
        if rate is not None:
            try:
                engine.setProperty("rate", int(rate))
            except Exception:
                pass
        if volume is not None:
            try:
                v: float = min(max(float(volume), 0.0), 1.0)
                engine.setProperty("volume", v)
            except Exception:
                pass
        engine.say(content)
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:
            pass
    except Exception as exc:
        return {
            "played": False,
            "reason": (
                f"離線播音失敗（{exc}）：請檢查音效卡／喇叭是否可用；"
                "無音效卡也不影響 fraud demo，請改看文字大字報。"
            ),
            "engine": "pyttsx3",
            "text": content,
        }
    return {"played": True, "engine": "pyttsx3", "text": content}


def write_wav_placeholder(
    path: str | Path,
    *,
    src: str | Path | None = None,
    sr: int = 16000,
    seconds: float = 1.0,
) -> dict[str, object]:
    """預錄台語 wav 佔位介面：決賽前把真人預錄檔灌進來用。

    用法：
        - 先佔位：``write_wav_placeholder("assets/ta_warning.wav")`` 寫 1 秒靜音，
          讓決賽流程（播檔分支）先跑通。
        - 決賽前灌檔：``write_wav_placeholder("assets/ta_warning.wav",
          src="錄好的阿嬤緊掛斷.wav")`` 直接複製覆蓋同路徑，
          之後播音分支優先播此檔即可（待決賽前接線）。

    Args:
        path: 佔位／預錄 wav 目標路徑（父目錄自動建立）。
        src: 已錄好的台語 wav；有給且存在就複製覆蓋，不做轉碼。
        sr: 佔位檔取樣率（Hz），預設 16000。
        seconds: 佔位靜音秒數，預設 1.0。

    Returns:
        ``{ok: True, path: ..., source: ...｜None, note: ...}``；
        參數非法時拋 ``ValueError``（建置期錯誤應早爆，不靜默）。
    """
    target: Path = Path(path)
    if not str(target):
        raise ValueError("目標路徑 path 不可為空。")
    if not isinstance(sr, int) or sr <= 0:
        raise ValueError(f"取樣率 sr 須為正整數，收到 {sr!r}。")
    if not isinstance(seconds, (int, float)) or not (float(seconds) > 0):
        raise ValueError(f"秒數 seconds 須為正數，收到 {seconds!r}。")
    target.parent.mkdir(parents=True, exist_ok=True)
    if src is not None and str(src):
        src_path: Path = Path(src)
        if src_path.is_file():
            shutil.copyfile(src_path, target)
            return {
                "ok": True,
                "path": str(target),
                "source": str(src_path),
                "note": (
                    "預錄台語 wav 已就位；決賽播音分支請優先播此檔，"
                    "無音效卡時照常降級為文字大字報，fraud demo 不中斷。"
                ),
            }
    nframes: int = max(1, int(sr * float(seconds)))
    with wave.open(str(target), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sr))
        wf.writeframes(b"\x00\x00" * nframes)
    return {
        "ok": True,
        "path": str(target),
        "sr": int(sr),
        "seconds": float(seconds),
        "source": None,
        "note": (
            "已寫入靜音佔位 wav；決賽前請用預錄台語 wav 以 src 參數覆蓋此檔，"
            "檔名與路徑保持不變即可接上播音分支。"
        ),
    }
