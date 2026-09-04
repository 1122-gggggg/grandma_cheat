"""即時麥克風串流：10 秒塊錄音 → 暫存 wav → 轉寫成 Segment。

設計說明（給跨領域隊友）：
- 有硬體時：``iter_mic_segments`` 用 sounddevice 一次錄一塊（預設 10 秒），
  存成暫存 wav 後調 ``Transcriber.transcribe`` 轉寫，鏈路完整可跑決賽即時版。
- 無硬體時：缺 sounddevice、缺麥克風、錄音失敗一律拋 ``RuntimeError``，
  錯誤訊息內含檢查清單與備份片指引；本模組絕不回傳假逐字稿，
  請上層接住例外後切離線備份片（``fraud demo``）。
- ``collect_window`` 是 10 秒滑動拼接：把 Segment 串的文字接起來，
  只留尾端 ``n_chars`` 字（約 10 秒講話量），給評分器吃。
- 本檔不碰 ``transcriber.py``／``vad.py``，只呼叫它們的公開介面。
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from typing import Iterable, Iterator

from antiscam.audio.transcriber import Transcriber
from antiscam.contracts import Segment

# 檢查清單：無硬體時錯誤訊息共用，測試會斷言含「sounddevice／麥克風／檢查」字樣。
_MIC_CHECKLIST: str = (
    "檢查清單："
    "1) 確認麥克風已接上並在系統音效設定中啟用（Linux 可跑 arecord -l 確認）；"
    "2) 確認已安裝 sounddevice 與 PortAudio"
    "（pip install sounddevice；Ubuntu 另需 sudo apt install libportaudio2）；"
    "3) 確認沒有其他程式獨佔麥克風，必要時重插或重開終端機；"
    "4) 無麥克風時請改跑離線備份片："
    "python -m antiscam.demo.runner --mode fraud（fraud demo 不需麥克風照常可跑）。"
    "本函式不回傳假逐字稿，請上層接住 RuntimeError 後切備份片。"
)


def _checklist_msg(reason: str) -> str:
    """組出帶檢查清單的錯誤訊息（reason 說明本次失敗原因）。"""
    return f"無法啟用麥克風即時辨識（{reason}）。{_MIC_CHECKLIST}"


def _write_mono_wav(path: str, samples: object, sr: int) -> None:
    """把單聲道浮點音訊寫成 16-bit PCM wav（只用標準庫 wave＋numpy）。"""
    try:
        import numpy as np
    except Exception:
        np = None  # type: ignore[assignment]
    if np is not None:
        arr = np.asarray(samples, dtype=np.float32).reshape(-1)
        pcm = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    else:  # 極端降級：numpy 缺席時用純 Python 轉換
        import struct

        flat = list(samples)  # type: ignore[arg-type]
        vals: list[int] = []
        for v in flat:
            try:
                f: float = float(v)  # type: ignore[arg-type]
            except Exception:
                f = 0.0
            f = min(max(f, -1.0), 1.0)
            vals.append(int(f * 32767.0))
        pcm = struct.pack(f"<{len(vals)}h", *vals) if vals else b""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sr))
        wf.writeframes(pcm)


def _has_input_device(sd: object) -> bool:
    """檢查 sounddevice 是否有可用麥克風輸入（任一裝置輸入聲道數 > 0）。"""
    try:
        devices = sd.query_devices()  # type: ignore[attr-defined]
    except Exception:
        return False
    try:
        for dev in devices:
            try:
                channels = int(dev.get("max_input_channels", 0))  # type: ignore[attr-defined]
            except Exception:
                continue
            if channels > 0:
                return True
    except Exception:
        return False
    return False


def iter_mic_segments(sr: int = 16000, block: float = 10.0) -> Iterator[Segment]:
    """從麥克風逐塊錄音並轉寫成 Segment（每塊 ``block`` 秒，預設 10 秒）。

    Args:
        sr: 取樣率（Hz），預設 16000。
        block: 每塊秒數，預設 10.0（與 10 秒滑動窗口對齊）。

    Returns:
        ``Iterator[Segment]``：無限串流，每塊錄完轉寫後逐段讓出；
        時間戳已偏移為絕對秒數（第 k 塊基底為 ``k * block``）。

    Raises:
        ValueError: 參數非法（取樣率或塊長非正數）。
        RuntimeError: 缺 sounddevice、缺麥克風、錄音失敗時拋出，
            訊息內含檢查清單；上層應接住後切離線備份片，不靜默假跑。

    使用範例（上層接住切備份片）：
        ``try: gen = iter_mic_segments() except RuntimeError: 跑 fraud 備份片``
    """
    if not isinstance(sr, int) or sr <= 0:
        raise ValueError(f"取樣率 sr 須為正整數，收到 {sr!r}。")
    if not isinstance(block, (int, float)) or not (float(block) > 0):
        raise ValueError(f"塊長 block 須為正數秒，收到 {block!r}。")
    sr_int: int = int(sr)
    block_f: float = float(block)

    # 預檢在呼叫當下就做（非 generator 延遲），缺件立刻拋，上層好切備份片。
    try:
        import sounddevice as sd  # 區域 import：缺件時才報錯，import 本模組不倒
    except Exception as exc:
        raise RuntimeError(_checklist_msg(f"缺少 sounddevice（{exc}）")) from exc
    if not _has_input_device(sd):
        raise RuntimeError(_checklist_msg("找不到可用麥克風輸入裝置"))

    return _record_loop(sd, sr_int, block_f)


def _record_loop(sd: object, sr: int, block: float) -> Iterator[Segment]:
    """實際錄音迴圈（無限產生器，由 ``iter_mic_segments`` 預檢後委派）。"""
    transcriber: Transcriber = Transcriber()
    frames: int = max(1, int(sr * block))
    index: int = 0
    while True:
        base: float = float(index * block)
        # 錄一塊：失敗（拔麥、獨佔、PortAudio 錯誤）轉成帶檢查清單的 RuntimeError。
        try:
            rec = sd.rec(frames, samplerate=sr, channels=1, dtype="float32")  # type: ignore[attr-defined]
            sd.wait()  # type: ignore[attr-defined]
        except Exception as exc:
            raise RuntimeError(
                _checklist_msg(f"錄音失敗（第 {index} 塊，{exc}）")
            ) from exc
        # 存暫存 wav → 轉寫 → 清檔；轉寫本身不拋錯（失敗回空 Segment）。
        tmp_path: str = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            _write_mono_wav(tmp_path, rec.reshape(-1), sr)
            segments: list[Segment] = transcriber.transcribe(tmp_path)
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass
        for seg in segments:
            try:
                text: str = str(getattr(seg, "text", "") or "")
                start: float = float(getattr(seg, "start", 0.0) or 0.0)
                end: float = float(getattr(seg, "end", 0.0) or 0.0)
                lang: str = str(getattr(seg, "lang", "") or "zh")
            except Exception:
                continue
            # 空佔位段（0, 0）補上本塊時間，保留空文字（誠實標示靜音／轉寫失敗）。
            if text == "" and start == 0.0 and end == 0.0:
                yield Segment(text="", start=base, end=base + block, lang=lang or "zh")
            else:
                yield Segment(
                    text=text,
                    start=base + start,
                    end=base + end,
                    lang=lang or "zh",
                )
        index += 1


def collect_window(gen: Iterable[Segment] | None, n_chars: int = 150) -> str:
    """10 秒滑動拼接：把 Segment 串的文字接起來，只留尾端 ``n_chars`` 字。

    Args:
        gen: Segment 可迭代物（串流產生器或串列皆可，``None`` 視為空）。
        n_chars: 窗口保留字數上限，預設 150（約 10 秒講話量）。

    Returns:
        拼接後的窗口文字（尾端 ``n_chars`` 字）；無內容回空字串，不拋錯。
    """
    if gen is None:
        return ""
    try:
        limit: int = int(n_chars)
    except Exception:
        limit = 150
    if limit <= 0:
        return ""
    parts: list[str] = []
    try:
        iterator = iter(gen)
    except Exception:
        return ""
    for seg in iterator:
        try:
            if seg is None:
                continue
            text: str = str(getattr(seg, "text", "") or "")
        except Exception:
            continue
        if text:
            parts.append(text)
    joined: str = "".join(parts)
    if len(joined) > limit:
        return joined[-limit:]
    return joined
