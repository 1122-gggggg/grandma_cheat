"""阿嬤的台語反詐守門員 — 離線 Demo 入口。

決賽現場（斷網）用：全程不需麥克風、不需網路、不載入音訊模型。
三種模式（`python -m antiscam.demo.runner --mode fraud|normal|interactive`）：

- fraud：播 3 段假檢警模擬逐字稿（台語夾雜）→ 調 Scorer → 大字報 → Notifier 寫 log。
- normal：播孫子問候逐字稿 → 綠燈通過（對照組）。
- interactive：評審當騙子打字，逐句即時評分。

本檔依賴只碰 contracts / brain / guardian，絕不 import 音訊模型。
10 秒滑動窗口在 demo 層做：這裡用字串拼接模擬（真機上改接 Transcriber 的 Segment）。
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from antiscam.contracts import Alert, ScoreResult, Segment

# ---- 腦組評分器：只碰 brain，不碰音訊模型 ----
try:
    from antiscam.brain.scorer import Scorer
except ImportError:
    try:
        from antiscam.brain import Scorer  # type: ignore[no-redef]
    except ImportError:
        Scorer = None  # type: ignore[no-redef,assignment]

# ---- 守門組大字報：decide(評分)->告警，render(評分)->大字報文字 ----
try:
    from antiscam.guardian.dashboard import decide, render
except ImportError:
    try:
        from antiscam.guardian import decide, render  # type: ignore[no-redef]
    except ImportError:
        decide = None  # type: ignore[no-redef,assignment]
        render = None  # type: ignore[no-redef,assignment]

# ---- 守門組通知器：只寫 local log，不打真網路 ----
try:
    from antiscam.guardian.notifier import Notifier
except ImportError:
    try:
        from antiscam.guardian import Notifier  # type: ignore[no-redef]
    except ImportError:
        Notifier = None  # type: ignore[no-redef,assignment]

# ---- 守門組台語警語：告警翻成唸給阿嬤聽的台語 ----
try:
    from antiscam.guardian.tts_text import to_ta_warning
except ImportError:
    try:
        from antiscam.guardian import to_ta_warning  # type: ignore[no-redef]
    except ImportError:
        to_ta_warning = None  # type: ignore[no-redef,assignment]


# ---- 守門組台語播音：pyttsx3 離線播，缺件/無音效卡回傳原因不拋錯 ----
try:
    from antiscam.guardian.player import speak_ta
except ImportError:
    try:
        from antiscam.guardian import speak_ta  # type: ignore[no-redef]
    except ImportError:
        speak_ta = None  # type: ignore[no-redef,assignment]

# ---- 音訊組音效：純標準庫蜂鳴音與電話鈴聲，安全播放 ----
try:
    from antiscam.audio.sound_effects import (
        generate_beep_wav,
        generate_ring_wav,
        play_wav_safe,
    )
except ImportError:
    try:
        from antiscam.audio import (  # type: ignore[no-redef]
            generate_beep_wav,
            generate_ring_wav,
            play_wav_safe,
        )
    except ImportError:
        generate_beep_wav = None  # type: ignore[no-redef,assignment]
        generate_ring_wav = None  # type: ignore[no-redef,assignment]
        play_wav_safe = None  # type: ignore[no-redef,assignment]

# 一行逐字稿 = (說話人, 內容, 開始秒, 結束秒, 語言標籤)
ScriptLine = tuple[str, str, float, float, str]


class ScorerLike(Protocol):
    """評分器介面：真的 Scorer 和降級關鍵詞版共用."""

    def score(self, text: str) -> ScoreResult:
        """評一段文字的可疑度."""
        ...


class NotifierLike(Protocol):
    """通知器介面：真的 Notifier 和只寫檔版共用."""

    def notify(self, alert: Alert) -> dict[str, object]:
        """發告警（只寫 local log），回傳寫檔結果."""
        ...


# ============================================================
# 模擬逐字稿（離線 demo 用，免麥克風、免網路）
# ============================================================

# fraud：假檢警，台語夾雜華語話術，3 段層層加壓
FRAUD_SCRIPT: list[ScriptLine] = [
    (
        "☎ 騙子",
        "阿嬤你好，我是台北地檢署的檢察官，你名下帳戶涉及洗錢案件，"
        "這馬已經分案偵辦，你莫緊張，照我講的做就好。",
        0.0,
        4.0,
        "mixed",
    ),
    (
        "☎ 騙子",
        "你的身分證予人冒用，帳戶已經變成警示戶，裡面的錢愛先領出來，"
        "匯到監管帳戶凍結保管，配合調查才袂有代誌。",
        4.0,
        8.5,
        "mixed",
    ),
    (
        "☎ 騙子",
        # 註：第 3 段單看「電話不要掛斷」關鍵詞很弱，必須靠 10 秒滑動窗口
        # 累積文字（含前段「地檢署／監管帳戶」）一起送進 score() 才判 fraud；
        # 因此每段顯示一律評窗口累積文字，不用單段文字評分。
        "這件代誌千萬袂使共別人講，連你孫仔嘛袂使講，電話不要掛斷，"
        "你這馬就去銀行匯錢，我會佇線頂陪你。",
        8.5,
        13.5,
        "mixed",
    ),
]

# normal：孫子問候，對照組，全程應該綠燈
NORMAL_SCRIPT: list[ScriptLine] = [
    (
        "👦 孫子阿明",
        "阿嬤，我是阿明啦，呷飽未？我這禮拜六轉去看你，欲煮你上愛呷的苦瓜湯。",
        0.0,
        4.0,
        "mixed",
    ),
    (
        "👦 孫子阿明",
        "阿公的藥仔有按時呷無？我買一箱牛奶寄轉去，你免出門提，佇厝裡等就好。",
        4.0,
        8.0,
        "mixed",
    ),
]

# 互動模式的離開指令（評審打這些字就結束）
QUIT_WORDS: set[str] = {"q", "quit", "exit", "離開", "結束"}

# 分數門檻：0.7 以上紅燈，0.4 以上黃燈，其餘綠燈
FRAUD_THRESHOLD: float = 0.7
SUSPICIOUS_THRESHOLD: float = 0.4


# ============================================================
# 降級零件：隊友模組缺席或斷網連不上時，靠這些保證離線可跑
# ============================================================


def _repo_root() -> Path:
    """從本檔位置往上找 pyproject.toml，那就是專案根目錄."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parents[3]


@dataclass
class _Pattern:
    """降級評分用的關鍵詞規則（一條詐騙話術）."""

    pid: str  # 規則編號，如 police-01
    category: str  # 類別：假檢警 / 假投資 / 假親友
    keywords: list[str] = field(default_factory=list)  # 華語 + 台羅關鍵詞
    weight: float = 0.0  # 命中這條話術的配分


def _load_keyword_patterns() -> list[_Pattern]:
    """讀 data/fraud_patterns.json；讀不到就回空串列（不炸掉）."""
    path: Path = _repo_root() / "data" / "fraud_patterns.json"
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    patterns: list[_Pattern] = []
    if not isinstance(raw, list):
        return []
    for item in raw:
        if not isinstance(item, dict):
            continue
        keywords: list[str] = [
            str(kw)
            for kw in list(item.get("keywords_zh", []))
            + list(item.get("keywords_ta", []))
        ]
        try:
            weight: float = float(item.get("weight", 0.0))
        except (TypeError, ValueError):
            weight = 0.0
        patterns.append(
            _Pattern(
                pid=str(item.get("id", "?")),
                category=str(item.get("category", "?")),
                keywords=[kw for kw in keywords if kw],
                weight=weight,
            )
        )
    return patterns


class _KeywordScorer:
    """降級版評分器：純關鍵詞規則，不用網路、不用 Ollama."""

    def __init__(self) -> None:
        """啟動時把關鍵詞庫載入記憶體."""
        self._patterns: list[_Pattern] = _load_keyword_patterns()

    def score(self, text: str) -> ScoreResult:
        """算可疑度：命中話術的配分加總，上限 1.0."""
        if not text.strip():
            return ScoreResult(
                score=0.0, label="safe", matched=[], reasons=["內容為空，視為安全"]
            )
        matched: list[str] = []
        reasons: list[str] = []
        total: float = 0.0
        for pattern in self._patterns:
            hits: list[str] = [kw for kw in pattern.keywords if kw and kw in text]
            if hits:
                total += pattern.weight
                matched.extend(hits)
                reasons.append(f"命中「{pattern.category}」話術{hits}（{pattern.pid}）")
        score: float = min(1.0, total)
        return ScoreResult(
            score=score, label=_label_for(score), matched=matched, reasons=reasons
        )


class _FileNotifier:
    """降級版通知器：告警寫成 JSONL 存本地，不打真網路."""

    def __init__(self, log_path: Path | None = None) -> None:
        """決定 log 檔位置，預設 logs/demo_alerts.log."""
        self.log_path: Path = log_path or (_repo_root() / "logs" / "demo_alerts.log")

    def notify(self, alert: Alert) -> dict[str, object]:
        """把告警加時間戳 append 到 log 檔，回傳寫檔結果."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, object] = {
            "time": datetime.now().isoformat(timespec="seconds"),
            **alert.to_dict(),
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"ok": True, "level": alert.level, "log_path": str(self.log_path)}


def _label_for(score: float) -> str:
    """分數轉標籤：和 contracts 的 safe / suspicious / fraud 對齊."""
    if score >= FRAUD_THRESHOLD:
        return "fraud"
    if score >= SUSPICIOUS_THRESHOLD:
        return "suspicious"
    return "safe"


def _fallback_alert(result: ScoreResult) -> Alert:
    """降級版 decide：只看分數門檻，給中 + 台雙語告警."""
    if result.score >= FRAUD_THRESHOLD:
        return Alert(
            level="danger",
            message_zh="偵測到高度疑似詐騙話術，請立即掛斷電話並與家人確認，切勿匯款。",
            message_ta="這通電話真可能是騙人的！錢袂使匯出去，先掛電話問家人！",
        )
    if result.score >= SUSPICIOUS_THRESHOLD:
        return Alert(
            level="warning",
            message_zh="偵測到可疑話術，請先不要匯款或提供個資，向家人或里長確認。",
            message_ta="這通電話怪怪，先莫匯錢，問家人抑是里長才決定！",
        )
    return Alert(
        level="info",
        message_zh="目前無偵測到詐騙話術，請放心通話。",
        message_ta="這通電話目前聽起來無問題，放心講落去。",
    )


def create_scorer() -> ScorerLike:
    """生評分器：腦組 Scorer 優先，建構失敗就降級關鍵詞版."""
    if Scorer is not None:
        try:
            return Scorer()  # type: ignore[no-any-return]
        except Exception:
            pass
    # 次路徑：腦組若是單檔 brain.py 且首輪 import 沒抓到，這裡再試一次
    try:
        module = importlib.import_module("antiscam.brain")
        scorer_cls = getattr(module, "Scorer", None)
        if scorer_cls is not None and scorer_cls is not Scorer:
            try:
                return scorer_cls()
            except Exception:
                pass
    except ImportError:
        pass
    return _KeywordScorer()


def create_notifier() -> NotifierLike:
    """生通知器：守門組 Notifier 優先，失敗就用只寫檔版."""
    if Notifier is not None:
        try:
            return Notifier()  # type: ignore[no-any-return]
        except Exception:
            pass
    return _FileNotifier()


# ============================================================
# 10 秒滑動窗口（demo 層）：字串拼接模擬
# ============================================================


class SlidingWindow:
    """10 秒滑動窗口：新逐字稿進來，掉出窗口的舊文字就丟掉."""

    def __init__(self, window_seconds: float = 10.0) -> None:
        """設定窗口長度（秒），預設 10 秒."""
        self.window_seconds: float = window_seconds
        self._segs: list[Segment] = []

    def add(self, seg: Segment) -> str:
        """吃進一段逐字稿，回傳窗口內累積文字（字串拼接）."""
        self._segs.append(seg)
        cutoff: float = seg.end - self.window_seconds
        self._segs = [s for s in self._segs if s.end > cutoff]
        return self.text

    @property
    def text(self) -> str:
        """窗口內文字全部接起來（中文不加空白，直接串接）."""
        return "".join(s.text for s in self._segs)


# ============================================================
# 評分 → 告警 → 大字報
# ============================================================


def score_text(
    scorer: ScorerLike, fallback: _KeywordScorer, text: str
) -> tuple[ScoreResult, bool]:
    """評一段文字；主評分器炸掉（Ollama 連不上等）就地降級.

    回傳 (評分結果, 是否為降級結果)。
    """
    try:
        return scorer.score(text), False
    except Exception:
        if scorer is fallback:
            return (
                ScoreResult(
                    score=0.0,
                    label="safe",
                    matched=[],
                    reasons=["評分失敗，保守視為安全"],
                ),
                True,
            )
        return fallback.score(text), True


def decide_alert(result: ScoreResult) -> Alert:
    """評分轉告警：守門組 decide 優先，缺席或炸掉用內建門檻."""
    if decide is not None:
        for candidate in (result, result.score):
            try:
                alert = decide(candidate)  # type: ignore[arg-type]
            except TypeError:
                continue  # 換一種參數型別再試一次
            except Exception:
                break  # decide 本體壞掉，直接降級
            else:
                if isinstance(alert, Alert):
                    return alert
                break
    return _fallback_alert(result)


# 終端機顏色碼（轉貼或無 tty 時自動關掉）
_RED: str = "\033[91m"
_YELLOW: str = "\033[93m"
_GREEN: str = "\033[92m"
_BOLD: str = "\033[1m"
_RESET: str = "\033[0m"


def _supports_color() -> bool:
    """有 tty 且沒設 NO_COLOR 才上色，錄影轉貼不亂碼."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _paint(text: str, color: str) -> str:
    """包 ANSI 顏色；不支援的環境原字回傳."""
    if not _supports_color():
        return text


def _try_guardian_render(result: ScoreResult) -> str | None:
    """試守門組 render；契約為 render(score)，一律吃窗口累積的 ScoreResult."""
    if render is None:
        return None
    for args in ((result,), (result.score,)):
        try:
            text = render(*args)  # type: ignore[arg-type]
        except TypeError:
            continue
        except Exception:
            return None
        else:
            return str(text)
    return None


def _banner_text(alert: Alert, result: ScoreResult) -> str:
    """內建大字報：紅 / 黃 / 綠三色，斷網也印得出來."""
    if alert.level == "danger":
        color: str = _RED
        title: str = "🛑 疑似詐騙！緊掛電話！ 🛑"
    elif alert.level == "warning":
        color = _YELLOW
        title = "⚠️ 有可疑話術！先莫匯錢！ ⚠️"
    else:
        color = _GREEN
        title = "✅ 目前安全，放心講落去 ✅"
    bar_len: int = 20
    filled: int = int(round(result.score * bar_len))
    bar: str = "█" * filled + "░" * (bar_len - filled)
    line: str = "═" * 38
    return (
        _paint(line, color)
        + "\n"
        + _paint(_BOLD + title.center(36) + _RESET, color)
        + "\n"
        + _paint(f"  可疑度 [{bar}] {result.score:.2f}（{result.label}）", color)
        + "\n"
        + _paint(line, color)
    )


def show_dashboard(alert: Alert, result: ScoreResult) -> None:
    """秀大字報：守門組 render(窗口 ScoreResult)優先，失敗才用內建版."""
    rendered: str | None = _try_guardian_render(result)
    print(rendered if rendered is not None else _banner_text(alert, result))


def _ta_from_label(label: str) -> str:
    """從 ScoreResult.label 推台語警語（to_ta_warning 缺席時的保底，不寫死正常句）."""
    kind: str = str(label or "").strip().lower()
    if kind in ("fraud", "danger", "high", "詐騙"):
        return "阿嬤，這是騙人的，緊掛斷！"
    if kind in ("suspect", "suspicious", "warn", "warning", "medium", "可疑"):
        return "阿嬤，這通有可疑，先毋通匯錢。"
    return "這通正常。"


def ta_warning(result: ScoreResult) -> str:
    """拿台語警語：契約為 to_ta_warning(kind)，一律吃窗口 ScoreResult 的 label."""
    if to_ta_warning is not None:
        for candidate in (result.label,):
            try:
                return str(to_ta_warning(candidate))  # type: ignore[arg-type]
            except Exception:
                continue
    return _ta_from_label(result.label)


def _send_alert(notifier: NotifierLike, alert: Alert) -> dict[str, object]:
    """發告警；真 Notifier 炸掉就改寫 demo log，demo 不中斷."""
    try:
        return dict(notifier.notify(alert))
    except Exception:
        return _FileNotifier().notify(alert)


# ============================================================
# 音效與語音輔助：純標準庫電話鈴聲、警報蜂鳴音與離線台語播報
# ============================================================


def _audio_cache_dir() -> Path:
    """取得音效快取目錄，優先使用 data/audio，失敗則使用系統暫存目錄."""
    try:
        candidate: Path = _repo_root() / "data" / "audio"
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except Exception:
        import tempfile

        fallback: Path = Path(tempfile.gettempdir()) / "antiscam_audio"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _get_or_generate_ring_wav() -> str | None:
    """取得或生成電話響鈴音（Ring tone 440Hz+480Hz）."""
    if generate_ring_wav is None:
        return None
    try:
        path: Path = _audio_cache_dir() / "ring.wav"
        if not path.is_file() or path.stat().st_size == 0:
            generate_ring_wav(str(path), duration=2.0)
        return str(path)
    except Exception:
        return None


def _get_or_generate_beep_wav() -> str | None:
    """取得或生成警報蜂鳴音（Warning beep 880Hz）."""
    if generate_beep_wav is None:
        return None
    try:
        path: Path = _audio_cache_dir() / "beep.wav"
        if not path.is_file() or path.stat().st_size == 0:
            generate_beep_wav(str(path), freq=880.0, duration=0.5, volume=0.5)
        return str(path)
    except Exception:
        return None


def play_ring_tone_if_enabled(enabled: bool) -> None:
    """若啟用音效，開場播放電話響鈴提示音（Ring tone），無硬體則降級為文字提示."""
    if not enabled:
        return
    print("🔔 [音效] 模擬電話撥入響鈴（Ring tone 440Hz+480Hz）...")
    ring_path: str | None = _get_or_generate_ring_wav()
    if not ring_path or play_wav_safe is None:
        print("（提示：未載入音效生成模組，已自動降級為文字提示）")
        return
    played: bool = play_wav_safe(ring_path)
    if not played:
        print("（提示：環境無可用音效輸出裝置，響鈴音已降級為文字提示）")


def trigger_fraud_alert_audio(result: ScoreResult, enabled: bool) -> None:
    """當判定為詐騙時觸發警報音效與台語播報，無音效設備時自動降級為文字提示."""
    if not enabled:
        return
    print("🚨 [音效] 觸發警報蜂鳴音 (Warning beep 880Hz)...")
    beep_path: str | None = _get_or_generate_beep_wav()
    beep_played: bool = False
    if beep_path and play_wav_safe is not None:
        beep_played = play_wav_safe(beep_path)
    if not beep_played:
        print("（提示：環境無可用音效輸出裝置，警報音已降級為文字提示）")

    ta_text: str = ta_warning(result)
    print(f"📢 [語音] 嘗試播報台語警語：『{ta_text}』...")
    if speak_ta is not None:
        try:
            voice_res: dict[str, object] = speak_ta(ta_text)
            if not voice_res.get("played"):
                reason: object = voice_res.get("reason", "無法播放語音")
                print(f"（提示：離線台語語音未播放 [{reason}]，已降級為文字大字報）")
        except Exception as exc:
            print(f"（提示：離線台語語音播放例外 [{exc}]，已降級為文字大字報）")
    else:
        print("（提示：未載入離線語音模組，已降級為文字大字報）")


# ============================================================
# 三種模式
# ============================================================


def _run_turn(
    scorer: ScorerLike,
    fallback: _KeywordScorer,
    window: SlidingWindow,
    index: int,
    line: ScriptLine,
    audio: bool = False,
) -> tuple[ScoreResult, Alert]:
    """跑一段逐字稿：進窗口 → 評窗口累積文字 → 轉告警 → 印大字報與明細."""
    speaker, text, start, end, lang = line
    seg: Segment = Segment(text=text, start=start, end=end, lang=lang)
    # 關鍵：評的是窗口內累積文字（window.add 回傳），不是單段 seg.text；
    # render / decide / to_ta_warning 全部吃同一個窗口 ScoreResult，不混用單段分數。
    window_text: str = window.add(seg)
    result, degraded = score_text(scorer, fallback, window_text)
    alert: Alert = decide_alert(result)
    print(
        f"\n── 第 {index} 段（{seg.start:.1f}s–{seg.end:.1f}s，窗口內累積 {len(window_text)} 字）──"
    )
    print(f"{speaker}：{seg.text}")
    if degraded:
        print("（註：主評分器連線失敗，已降級為關鍵詞規則）")
    show_dashboard(alert, result)
    print(f"分數：{result.score:.2f}（{result.label}）")
    if result.matched:
        print("命中：" + "、".join(result.matched))
    for reason in result.reasons:
        print(f"理由：{reason}")
    print(f"台語警語：{ta_warning(result)}")

    # 當判定為詐騙（fraud）時，觸發警報音效與台語播音
    if audio and (result.label == "fraud" or alert.level == "danger"):
        trigger_fraud_alert_audio(result, audio)

    return result, alert


def run_fraud(
    scorer: ScorerLike,
    notifier: NotifierLike,
    window_seconds: float = 10.0,
    audio: bool = False,
) -> int:
    """fraud 模式：3 段假檢警逐字稿 → 評分 → 大字報 → 寫 log."""
    window: SlidingWindow = SlidingWindow(window_seconds)
    print("【fraud 模式】模擬來電：假檢警（台語夾雜），免麥克風、免網路。")
    play_ring_tone_if_enabled(audio)
    last_result: ScoreResult | None = None
    last_alert: Alert | None = None
    for i, line in enumerate(FRAUD_SCRIPT, 1):
        last_result, last_alert = _run_turn(
            scorer, _fallback_of(scorer), window, i, line, audio=audio
        )
    assert last_result is not None and last_alert is not None
    # 總結台語警語一律從最終窗口 ScoreResult 的 label 推導，不寫死正常句。
    print(
        f"\n【總結】3 段播完，最終分數 {last_result.score:.2f}（{last_result.label}）。"
    )
    print(f"台語警語：{ta_warning(last_result)}")
    info: dict[str, object] = _send_alert(notifier, last_alert)
    print(f"告警已寫入 local log：{info.get('log_path', info)}（未打真網路）")
    return 0


def run_normal(
    scorer: ScorerLike,
    notifier: NotifierLike,
    window_seconds: float = 10.0,
    audio: bool = False,
) -> int:
    """normal 模式：孫子問候對照組，全程綠燈，不發告警."""
    del notifier  # 綠燈不需通知，保留參數只是讓三模式介面一致
    window: SlidingWindow = SlidingWindow(window_seconds)
    print("【normal 模式】模擬來電：孫子問候（對照組），應該全程綠燈。")
    play_ring_tone_if_enabled(audio)
    for i, line in enumerate(NORMAL_SCRIPT, 1):
        _run_turn(scorer, _fallback_of(scorer), window, i, line, audio=audio)
    print("\n【總結】全程綠燈，無需告警，阿嬤放心講。")
    return 0


def run_interactive(
    scorer: ScorerLike,
    notifier: NotifierLike,
    window_seconds: float = 10.0,
    audio: bool = False,
) -> int:
    """interactive 模式：評審當騙子打字，逐句即時評分."""
    window: SlidingWindow = SlidingWindow(window_seconds)
    fallback: _KeywordScorer = _fallback_of(scorer)
    print("【interactive 模式】請評審當騙子：直接打字，逐句即時評分。")
    print("範例：『我是地檢署檢察官，你的帳戶涉及洗錢』或『阿嬤我出車禍，趕快匯錢』。")
    print("輸入 q 或「離開」結束。")
    play_ring_tone_if_enabled(audio)
    clock: float = 0.0
    count: int = 0
    while True:
        try:
            line_text: str = input("\n騙子說（q 離開）> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n【結束】互動 demo 結束，多謝評審鬥陣玩！")
            break
        if line_text.lower() in QUIT_WORDS or line_text in QUIT_WORDS:
            print("【結束】互動 demo 結束，多謝評審鬥陣玩！")
            break
        if not line_text:
            continue
        count += 1
        clock += 3.0  # 每句當 3 秒（模擬時間戳，不需麥克風）
        _, alert = _run_turn(
            scorer,
            fallback,
            window,
            count,
            ("🎤 評審", line_text, clock - 3.0, clock, "mixed"),
            audio=audio,
        )
        if alert.level == "danger":
            info = _send_alert(notifier, alert)
            print(f"🔴 已達紅線，告警寫入 local log：{info.get('log_path', info)}")
    return 0


def _fallback_of(scorer: ScorerLike) -> _KeywordScorer:
    """拿降級評分器：主評分器本身就是關鍵詞版就直接用."""
    if isinstance(scorer, _KeywordScorer):
        return scorer
    return _KeywordScorer()


def _print_header(mode: str, audio: bool = False) -> None:
    """印開場頭：品名 + 斷網聲明 + 模式."""
    print("=" * 42)
    print("  阿嬤的台語反詐守門員 — 離線 Demo")
    print("  全程免麥克風、免網路（斷網可跑，禁中資模型）")
    print(f"  模式：{mode} | 音效：{'啟用 (--audio)' if audio else '停用'}")
    print("=" * 42)


def build_parser() -> argparse.ArgumentParser:
    """命令列參數：只收 mode、窗口秒數與音效開關，評審好操作."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m antiscam.demo.runner",
        description="阿嬤的台語反詐守門員 — 離線 Demo（fraud / normal / interactive）",
    )
    parser.add_argument(
        "--mode",
        choices=("fraud", "normal", "interactive"),
        default="fraud",
        help="fraud=假檢警展示，normal=孫子問候對照，interactive=評審打字互動",
    )
    parser.add_argument(
        "--window-seconds",
        type=float,
        default=10.0,
        help="滑動窗口長度（秒），預設 10.0",
    )
    parser.add_argument(
        "--audio",
        action="store_true",
        default=False,
        help="啟用通話音效與台語播報（開場響鈴、警報蜂鳴音、語音提示）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Demo 進入點：組裝評分器與通知器，分派三種模式."""
    args = build_parser().parse_args(argv)
    _print_header(args.mode, audio=args.audio)
    scorer: ScorerLike = create_scorer()
    notifier: NotifierLike = create_notifier()
    if args.mode == "fraud":
        return run_fraud(scorer, notifier, args.window_seconds, audio=args.audio)
    if args.mode == "normal":
        return run_normal(scorer, notifier, args.window_seconds, audio=args.audio)
    return run_interactive(scorer, notifier, args.window_seconds, audio=args.audio)


if __name__ == "__main__":
    raise SystemExit(main())
