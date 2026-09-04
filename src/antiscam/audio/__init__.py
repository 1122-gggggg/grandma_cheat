"""音訊子套件：VAD 切窗與語音轉寫。"""

from antiscam.audio.transcriber import Transcriber
from antiscam.audio.vad import split_window

__all__ = ["Transcriber", "split_window"]
