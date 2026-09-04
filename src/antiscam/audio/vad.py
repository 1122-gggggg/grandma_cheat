"""能量 VAD：把長音訊切成 10 秒滑動窗口，靜音窗口直接跳過。

設計說明（給跨領域隊友）：
- 輸入是單聲道（或立體聲自動轉單聲道）取樣點陣列與取樣率。
- 每 10 秒一個窗口（不足 10 秒的尾巴自成一個窗口）。
- 每個窗口內再切小幀（30ms）算能量，太安靜的幀算靜音；
  若窗口內「有聲音幀」比例太低，整個窗口視為靜音並跳過。
- 任何異常輸入（空陣列、None、非法取樣率）一律回傳空 list，不拋錯，
  讓 demo 層不斷線。
"""

from __future__ import annotations

import numpy as np


def split_window(samples: np.ndarray, sr: int) -> list[tuple[int, int]]:
    """把音訊切成 10 秒窗口，回傳 ``[(起始取樣點, 結束取樣點), ...]``。

    Args:
        samples: 音訊取樣點，一維或多維（多維會先平均成單聲道）。
        sr: 取樣率（Hz），須為正整數。

    Returns:
        非靜音窗口的 ``(start, end)`` 取樣點索引區間；
        輸入為空、靜音或非法時回傳空 list（不拋錯）。
    """
    # 防呆：型別/空值一律回空 list，不拋錯
    if samples is None:
        return []
    try:
        arr: np.ndarray = np.asarray(samples)
    except Exception:
        return []
    if arr.size == 0:
        return []
    if not isinstance(sr, (int, np.integer)) or int(sr) <= 0:
        return []
    sr_int: int = int(sr)

    # 正規化成單聲道 float32，並把 NaN/Inf 清掉
    try:
        mono: np.ndarray = _to_mono_float32(arr)
    except Exception:
        return []
    if mono.size == 0:
        return []
    mono = np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0)

    # 10 秒窗口長度（取樣點數）
    window_len: int = 10 * sr_int
    if window_len <= 0:
        return []

    # 幀參數：30ms 幀長、10ms 幀移，皆至少 1 點
    frame_len: int = max(1, int(sr_int * 0.030))
    frame_hop: int = max(1, int(sr_int * 0.010))
    # 能量門檻（正規化振幅下的 RMS）與最少有聲幀比例
    energy_thresh: float = 0.01
    min_speech_ratio: float = 0.10

    windows: list[tuple[int, int]] = []
    total: int = int(mono.shape[0])
    for start in range(0, total, window_len):
        end: int = min(start + window_len, total)
        chunk: np.ndarray = mono[start:end]
        if chunk.size == 0:
            continue
        # 太短的尾巴（不足 1 幀）若幾乎無聲則跳過
        if not _has_speech(
            chunk, frame_len, frame_hop, energy_thresh, min_speech_ratio
        ):
            continue
        windows.append((int(start), int(end)))
    return windows


def _to_mono_float32(arr: np.ndarray) -> np.ndarray:
    """把任意整數/浮點音訊轉成單聲道 float32（振幅約 -1~1）。"""
    a: np.ndarray = np.asarray(arr)
    # 多維（立體聲等）：沿最後一軸平均成單聲道
    if a.ndim > 1:
        a = np.mean(a, axis=-1)
    a = np.ravel(a).astype(np.float32, copy=False)
    # 整數 PCM（常見 int16/int32）正規化到 [-1, 1]
    if np.issubdtype(np.asarray(arr).dtype, np.integer):
        info_max: float = float(np.iinfo(np.asarray(arr).dtype).max)
        if info_max > 0:
            a = (a / info_max).astype(np.float32, copy=False)
    return a


def _has_speech(
    chunk: np.ndarray,
    frame_len: int,
    frame_hop: int,
    energy_thresh: float,
    min_speech_ratio: float,
) -> bool:
    """判斷一個窗口內是否有足夠比例的有聲幀（能量 VAD）。"""
    n: int = int(chunk.shape[0])
    if n == 0:
        return False
    # 全零（純靜音）快速路徑
    try:
        if not np.any(chunk):
            return False
    except Exception:
        return False
    # 逐幀算 RMS，統計超過門檻的幀比例
    speech_frames: int = 0
    total_frames: int = 0
    for fstart in range(0, n, frame_hop):
        fend: int = min(fstart + frame_len, n)
        frame: np.ndarray = chunk[fstart:fend]
        if frame.size == 0:
            continue
        total_frames += 1
        # RMS 能量
        try:
            rms: float = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
        except Exception:
            continue
        if rms >= energy_thresh:
            speech_frames += 1
        # 剩餘幀不足以翻盤可提早結束（省 CPU）
        # 這裡不做早停以保持邏輯簡單，筆電 CPU 也夠快
    if total_frames == 0:
        return False
    return (speech_frames / total_frames) >= min_speech_ratio
