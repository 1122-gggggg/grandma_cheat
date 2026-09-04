"""語音轉寫：優先 faster-whisper，失敗自動降級為空 Segment（不崩）。

設計說明（給跨領域隊友）：
- import 本模組不會下載模型、不會連網（lazy load：第一次 transcribe 才載入）。
- 筆電 CPU 優先：預設 device=cpu、compute_type=int8。
- 國台夾雜：固定 language=zh，並用 initial_prompt 提示模型注意台語詐騙詞。
- 任何失敗（無檔、模型載入失敗、辨識例外）一律回傳
  ``[Segment(text='', start=0.0, end=0.0, lang='zh')]``，不斷線。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from antiscam.contracts import Segment

# 國台夾雜提示詞：告訴模型這是國台語混合電話錄音，並列出常見詐騙關鍵詞，
# 提升檢察官/監管帳戶/匯款/投資穩賺/阿嬤金孫等詞的辨識率。
_INITIAL_PROMPT: str = (
    "這是台灣國語和台語夾雜的電話錄音逐字稿，"
    "可能提到檢察官、警察、法官、監管帳戶、凍結帳戶、"
    "匯款、匯錢、提款卡、投資、穩賺不賠、保證獲利、"
    "假檢警、假投資、假親友、阿嬤、金孫、借錢、周轉、"
    "檢察官啦、警察啦、匯錢啦、凍結啦。"
)

# 空結果：任何失敗路徑的統一回傳，避免上層崩潰
_EMPTY_SEGMENT_KWARGS: dict[str, Any] = {
    "text": "",
    "start": 0.0,
    "end": 0.0,
    "lang": "zh",
}


class Transcriber:
    """語音轉文字轉寫器（lazy load：建構與 import 時不載模型）。"""

    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        """初始化轉寫器（只記參數，不載模型）。

        Args:
            model_size: faster-whisper 模型名稱，預設 large-v3-turbo。
            device: 運算裝置，筆電優先用 cpu。
            compute_type: 量化型別，cpu 建議用 int8 省記憶體。
        """
        self.model_size: str = model_size
        self.device: str = device
        self.compute_type: str = compute_type
        self._model: Any = None  # 延遲載入，import/建構時保持 None

    def _load_model(self) -> Any | None:
        """延遲載入 faster-whisper 模型，失敗回傳 None（不拋錯）。"""
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # 區域 import：保持頂層 import 輕量
        except Exception:
            return None
        try:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        except Exception:
            self._model = None
        return self._model

    def transcribe(self, wav_path: str) -> list[Segment]:
        """把 wav 檔轉成 Segment 串列，失敗回空 Segment（不拋錯）。

        Args:
            wav_path: wav 音檔路徑。

        Returns:
            成功時為辨識出的 ``[Segment, ...]``（lang 皆為 zh）；
            無檔或任何失敗時為 ``[Segment(text='', ...)]``。
        """
        # 防呆：空字串/非字串/不存在檔案直接回空結果
        try:
            if not isinstance(wav_path, str) or not wav_path:
                return [Segment(**_EMPTY_SEGMENT_KWARGS)]
            if not Path(wav_path).is_file():
                return [Segment(**_EMPTY_SEGMENT_KWARGS)]
        except Exception:
            return [Segment(**_EMPTY_SEGMENT_KWARGS)]

        model: Any | None = self._load_model()
        if model is None:
            return [Segment(**_EMPTY_SEGMENT_KWARGS)]

        try:
            segments_iter: Any
            segments_iter, _info = model.transcribe(
                wav_path,
                language="zh",  # 國台夾雜以中文為主，台語靠 prompt 提示
                initial_prompt=_INITIAL_PROMPT,
            )
            out: list[Segment] = []
            for seg in segments_iter:
                try:
                    text: str = str(getattr(seg, "text", "") or "").strip()
                    start: float = float(getattr(seg, "start", 0.0) or 0.0)
                    end: float = float(getattr(seg, "end", 0.0) or 0.0)
                except Exception:
                    continue
                out.append(Segment(text=text, start=start, end=end, lang="zh"))
            if not out:
                return [Segment(**_EMPTY_SEGMENT_KWARGS)]
            return out
        except Exception:
            return [Segment(**_EMPTY_SEGMENT_KWARGS)]

    def stream(self) -> Iterator[Segment]:
        """麥克風即時串流（尚未實作的 stub）。

        Raises:
            NotImplementedError: 永遠拋出，提醒決賽前再實作。

        Returns:
            不回傳任何東西（stub）。
        """
        # TODO: 麥克風即時串流（sounddevice 抓音 -> VAD 切窗 -> transcribe），
        # 決賽斷網 demo 若要真即時再實作；目前 MVP 只需離線 wav 轉寫。
        raise NotImplementedError(
            "TODO: 麥克風即時串流尚未實作（stub），MVP 僅支援離線 transcribe()"
        )
