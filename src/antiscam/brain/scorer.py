"""詐騙評分器：關鍵詞加權為主，Ollama Gemma-TAIDE 複核為輔。

- 筆電 CPU 就能跑：沒有 Ollama 時只用關鍵詞，一樣給分。
- Ollama 連不上（例如斷網 demo）會靜默降級，不丟例外、不重試。
"""

import json
import re
import urllib.request

from antiscam.brain.patterns import BUILTIN_PATTERNS, load_patterns, match_keywords
from antiscam.contracts import ScoreResult

# Ollama 上的 Gemma-TAIDE 模型名稱（需事先 `ollama pull gemma-taide`）。
_OLLAMA_MODEL = "gemma-taide"

# 送給 LLM 的字數上限，避免筆電 CPU 等太久。
_MAX_TEXT_CHARS = 500


class Scorer:
    """詐騙評分器：`score(text)` 回傳 0~1 的詐騙分數與標籤。"""

    def __init__(
        self,
        patterns_path: str = "data/fraud_patterns.json",
        ollama_url: str = "http://localhost:11434",
        timeout: float = 2.0,
    ) -> None:
        """初始化評分器。

        :param patterns_path: 詐騙樣板 JSON 路徑，缺檔時改用內建保底。
        :param ollama_url: Ollama 服務位址，連不上會自動降級為純關鍵詞。
        :param timeout: Ollama 請求逾時秒數（只試一次，不重試）。
        """
        loaded: list[dict] = load_patterns(patterns_path)
        self._patterns: list[dict] = list(loaded) if loaded else list(BUILTIN_PATTERNS)
        self._examples: dict[str, str] = {
            str(p.get("id", "")): str(p.get("example", "")) for p in self._patterns
        }
        self._ollama_url: str = ollama_url.rstrip("/")
        self._timeout: float = timeout

    def score(self, text: str) -> ScoreResult:
        """為一段通話文字打分數。

        先做關鍵詞加權總和（clip 到 0~1），再請 Ollama 做二次確認；
        Ollama 連不上就靜默降級，只用關鍵詞分數。
        """
        if not isinstance(text, str) or not text.strip():
            return ScoreResult(
                score=0.0,
                label="safe",
                matched=[],
                reasons=["輸入為空，直接視為安全。"],
            )

        hits: list[tuple[str, float]] = match_keywords(text, self._patterns)
        matched: list[str] = [pid for pid, _ in hits]
        keyword_score: float = min(1.0, max(0.0, sum(w for _, w in hits)))
        label: str = self._label_of(keyword_score)
        if hits:
            reasons: list[str] = [
                f"命中「{pid}」：{self._examples.get(pid, '')}".rstrip("：")
                for pid in matched
            ]
        else:
            reasons = ["沒有命中任何詐騙關鍵詞。"]

        # Ollama 二次確認：只試一次，失敗就維持關鍵詞分數。
        llm_score, llm_note = self._ollama_check(text)
        final: float = keyword_score
        if llm_score is not None:
            reasons.append(llm_note)
            # LLM 只能把「可疑」往上確認為詐騙，不推翻關鍵詞的 fraud/safe，
            # 避免誤報打擾阿嬤的日常聊天。
            if llm_score >= 0.8 and label == "suspect":
                final = 0.8
                label = "fraud"
                reasons.append("Gemma-TAIDE 複核判定為詐騙，升級為 fraud。")

        final = min(1.0, max(0.0, final))
        return ScoreResult(score=final, label=label, matched=matched, reasons=reasons)

    @staticmethod
    def _label_of(score: float) -> str:
        """分數轉標籤：<0.4 安全，<0.8 可疑，>=0.8 詐騙。"""
        if score < 0.4:
            return "safe"
        if score < 0.8:
            return "suspect"
        return "fraud"

    def _ollama_check(self, text: str) -> tuple[float | None, str]:
        """呼叫 Ollama 做二次確認；連不上就回傳 (None, '')，不重試。"""
        try:
            prompt: str = (
                "你是「阿嬤的台語反詐守門員」，判斷以下通話文字是否為詐騙。"
                "只回一行「分數：0.x」（0=安全，1=詐騙），不要解釋。"
                f"通話文字：{text[:_MAX_TEXT_CHARS]}"
            )
            payload: bytes = json.dumps(
                {"model": _OLLAMA_MODEL, "prompt": prompt, "stream": False}
            ).encode("utf-8")
            req = urllib.request.Request(
                self._ollama_url + "/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="ignore"))
            llm_text: str = str(body.get("response", ""))
            parsed: float | None = self._parse_llm_score(llm_text)
            if parsed is None:
                return None, ""
            return parsed, f"Gemma-TAIDE 二次確認分數：{parsed:.2f}。"
        except Exception:
            # 靜默降級：沒裝 Ollama、斷網、模型不存在都走這裡。
            return None, ""

    @staticmethod
    def _parse_llm_score(llm_text: str) -> float | None:
        """從 LLM 回覆解析 0~1 分數；解析不出來就回 None。"""
        m = re.search(r"分數\s*[：:]\s*(0?\.\d+|[01](?:\.0+)?)", llm_text)
        if m:
            try:
                return min(1.0, max(0.0, float(m.group(1))))
            except ValueError:
                return None
        nums: list[str] = re.findall(r"\b(0?\.\d+|[01](?:\.0+)?)\b", llm_text)
        for raw in reversed(nums):
            try:
                return min(1.0, max(0.0, float(raw)))
            except ValueError:
                continue
        if "詐騙" in llm_text or "可疑" in llm_text:
            return 0.85
        if "安全" in llm_text or "正常" in llm_text:
            return 0.15
        return None
