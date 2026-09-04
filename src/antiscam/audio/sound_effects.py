"""音效生成與安全播放模組：純 Python 標準庫實作，零外部音訊依賴。

提供：
1. generate_beep_wav: 生成警示蜂鳴音（單頻正弦波，含平滑淡入淡出防爆音）。
2. generate_ring_wav: 生成電話撥入鈴聲雙頻音（440Hz + 480Hz 雙音複頻）。
3. play_wav_safe: 跨平台安全播放音檔（優先系統命令 aplay/paplay/afplay，無硬體安全靜默降級）。
"""

from __future__ import annotations

import math
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import wave


def generate_beep_wav(
    path: str,
    freq: float = 880.0,
    duration: float = 0.5,
    volume: float = 0.5,
    sample_rate: int = 16000,
) -> str:
    """生成警示蜂鳴音 wav 檔案。

    Args:
        path: 輸出的 wav 檔案路徑。
        freq: 蜂鳴音頻率（Hz），預設 880.0（A5 高音警示音）。
        duration: 音訊長度（秒），預設 0.5 秒。
        volume: 音量大小（0.0 ~ 1.0），預設 0.5。
        sample_rate: 取樣率（Hz），預設 16000。

    Returns:
        實際寫入的檔案路徑字串。
    """
    out_path: Path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dur: float = max(0.0, float(duration))
    vol: float = max(0.0, min(1.0, float(volume)))
    sr: int = max(1, int(sample_rate))
    n_samples: int = int(dur * sr)

    # 10ms 平滑淡入淡出，避免音訊開頭與結尾爆音 (pop/click)
    fade_len: int = min(int(0.01 * sr), n_samples // 4) if n_samples > 0 else 0
    frames: bytearray = bytearray()

    for i in range(n_samples):
        if fade_len > 0 and i < fade_len:
            env: float = i / fade_len
        elif fade_len > 0 and i > n_samples - fade_len:
            env = (n_samples - i) / fade_len
        else:
            env = 1.0

        sample_val: float = vol * env * math.sin(2.0 * math.pi * freq * (i / sr))
        int_val: int = max(-32768, min(32767, int(round(sample_val * 32767.0))))
        frames.extend(struct.pack("<h", int_val))

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(frames)

    return str(out_path)


def generate_ring_wav(
    path: str,
    duration: float = 2.0,
    volume: float = 0.5,
    sample_rate: int = 16000,
) -> str:
    """生成電話撥入鈴聲雙頻音（440Hz + 480Hz）wav 檔案。

    標準電話局撥入鈴聲採用 440Hz 與 480Hz 雙音複頻疊加。

    Args:
        path: 輸出的 wav 檔案路徑。
        duration: 音訊長度（秒），預設 2.0 秒。
        volume: 音量大小（0.0 ~ 1.0），預設 0.5。
        sample_rate: 取樣率（Hz），預設 16000。

    Returns:
        實際寫入的檔案路徑字串。
    """
    out_path: Path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dur: float = max(0.0, float(duration))
    vol: float = max(0.0, min(1.0, float(volume)))
    sr: int = max(1, int(sample_rate))
    n_samples: int = int(dur * sr)

    # 15ms 平滑淡入淡出
    fade_len: int = min(int(0.015 * sr), n_samples // 4) if n_samples > 0 else 0
    frames: bytearray = bytearray()

    for i in range(n_samples):
        if fade_len > 0 and i < fade_len:
            env: float = i / fade_len
        elif fade_len > 0 and i > n_samples - fade_len:
            env = (n_samples - i) / fade_len
        else:
            env = 1.0

        t: float = i / sr
        # 440Hz + 480Hz 雙音複頻合成
        dual_tone: float = 0.5 * (
            math.sin(2.0 * math.pi * 440.0 * t) + math.sin(2.0 * math.pi * 480.0 * t)
        )
        sample_val: float = vol * env * dual_tone
        int_val: int = max(-32768, min(32767, int(round(sample_val * 32767.0))))
        frames.extend(struct.pack("<h", int_val))

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(frames)

    return str(out_path)


def play_wav_safe(path: str) -> bool:
    """跨平台安全播放音檔。

    優先嘗試系統內建命令如 Linux aplay/paplay/pw-play、macOS afplay、
    Windows winsound。
    若無播放硬體、找不到指令或播放失敗，安全靜默回傳 False，不拋出例外崩潰。

    Args:
        path: 要播放的 wav 檔案路徑。

    Returns:
        True 代表播放成功，False 代表無法播放或播放失敗。
    """
    try:
        target: Path = Path(path)
        if not target.is_file():
            return False
    except Exception:
        return False

    sys_name: str = platform.system().lower()

    # Windows 原生標準庫播放器
    if sys_name == "windows":
        try:
            import winsound

            winsound.PlaySound(str(target), winsound.SND_FILENAME)
            return True
        except Exception:
            pass

    # macOS / Linux 命令列播放器候選清單
    candidates: list[list[str]] = []
    if sys_name == "darwin":
        candidates.append(["afplay", str(target)])
    else:
        # Linux / BSD / 其他
        candidates.append(["aplay", "-q", str(target)])
        candidates.append(["paplay", str(target)])
        candidates.append(["pw-play", str(target)])
        candidates.append(["afplay", str(target)])

    for cmd in candidates:
        exe: str | None = shutil.which(cmd[0])
        if not exe:
            continue
        try:
            proc = subprocess.run(
                [exe] + cmd[1:],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10.0,
                check=False,
            )
            if proc.returncode == 0:
                return True
        except Exception:
            continue

    return False
