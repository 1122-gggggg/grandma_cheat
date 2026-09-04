"""阿嬤的台語反詐守門員 — 全螢幕客廳守護看板 Web 伺服器。

使用純 Python 標準庫 http.server 與 urllib（零外部 Web 框架依賴），
專為客廳大字報看板與展場 Demo 設計。

API 端點：
- GET  /              : 載入客廳守護看板主頁面 (index.html)
- GET  /api/scenarios : 回傳內建的示範通話劇本清單
- GET  /api/health    : 伺服器健康檢查
- POST /api/score     : 接收通話文字，進行詐騙評分、告警判定、通關密語提示與 LINE 模擬推送
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# 確保 src 在 sys.path 中
_CURRENT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _CURRENT_DIR.parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from antiscam.contracts import Alert, ScoreResult  # noqa: E402

# 腦組評分器
try:
    from antiscam.brain.scorer import Scorer
except ImportError:
    Scorer = None  # type: ignore[assignment,misc]

# 話術樣板
try:
    from antiscam.brain.patterns import BUILTIN_PATTERNS, load_patterns
except ImportError:
    BUILTIN_PATTERNS = []

    def load_patterns(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


# 守門組大字報判定
try:
    from antiscam.guardian.dashboard import decide
except ImportError:

    def decide(score: ScoreResult | None) -> Alert:
        """降級版 decide。"""
        s = getattr(score, "score", 0.0) if score else 0.0
        if s >= 0.8:
            return Alert(
                level="danger",
                message_zh="高風險詐騙",
                message_ta="阿嬤，這是騙人的，緊掛斷！",
            )
        if s >= 0.4:
            return Alert(
                level="warning",
                message_zh="可疑電話",
                message_ta="阿嬤，這通有可疑，先毋通匯錢。",
            )
        return Alert(level="info", message_zh="正常通話", message_ta="這通正常。")


# 守門組 LINE 模擬推送
try:
    from antiscam.guardian.notifier import Notifier
except ImportError:

    class Notifier:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def notify(self, alert: Alert | None) -> dict[str, Any]:
            return {"level": getattr(alert, "level", "info"), "mock": True}


def get_passcode_prompt(
    score: ScoreResult, question: str = "咱家的狗叫啥名？"
) -> dict[str, Any]:
    """取得家庭通關密語反向驗證提示。

    優先嘗試從 guardian.passcode 或 guardian 匯入，若未就緒則使用相容保底實作。
    """
    try:
        from antiscam.guardian.passcode import get_passcode_prompt as _fn  # type: ignore[import-not-found]

        return _fn(score, question=question)  # type: ignore[no-any-return]
    except (ImportError, AttributeError):
        pass

    try:
        from antiscam.guardian import get_passcode_prompt as _fn  # type: ignore[attr-defined]

        return _fn(score, question=question)  # type: ignore[no-any-return]
    except (ImportError, AttributeError):
        pass

    # 保底實作：與 PatternPasscodeWorker 契約規格完全一致
    label = getattr(score, "label", "safe")
    score_val = getattr(score, "score", 0.0)
    if label == "fraud" or score_val >= 0.8:
        return {
            "triggered": True,
            "question": question,
            "prompt_ta": f"阿嬤莫慌！先問伊通關密語：『{question}』",
            "prompt_zh": f"防詐密語提示：請長輩詢問對方「{question}」反向驗證身份",
        }
    return {"triggered": False}


def extract_highlight_keywords(
    text: str, patterns: list[dict[str, Any]] | None = None
) -> list[str]:
    """從通話文字中提取命中或符合的關鍵詞以供前端醒目紅底標示。"""
    if not text or not text.strip():
        return []
    if patterns is None:
        try:
            patterns = load_patterns() or BUILTIN_PATTERNS
        except Exception:
            patterns = BUILTIN_PATTERNS

    hits: list[str] = []
    text_lower = text.lower()
    for p in patterns:
        if not isinstance(p, dict):
            continue
        keywords = list(p.get("keywords_zh", []) or []) + list(
            p.get("keywords_ta", []) or []
        )
        for kw in keywords:
            if not kw:
                continue
            kw_str = str(kw).strip()
            if len(kw_str) >= 2 and kw_str.lower() in text_lower:
                if kw_str not in hits:
                    hits.append(kw_str)

    # 依長度降冪排序，確保長詞優先被替換高亮
    hits.sort(key=len, reverse=True)
    return hits


# 內建示範劇本
DEFAULT_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "fraud_prosecutor",
        "category": "假檢警",
        "title": "播假檢警電話（層層加壓）",
        "description": "冒充地檢署檢察官，宣稱涉入洗錢案、要求資金監管，並嚴禁告知家人與掛斷電話。",
        "risk_level": "fraud",
        "turns": [
            {
                "speaker": "☎ 假檢警",
                "text": "阿嬤你好，我是台北地檢署的檢察官，你名下帳戶涉及洗錢案件，這馬已經分案偵辦，你莫緊張，照我講的做就好。",
                "delay_ms": 2500,
            },
            {
                "speaker": "☎ 假檢警",
                "text": "你的身分證予人冒用，帳戶已經變成警示戶，裡面的錢愛先領出來，匯到監管帳戶凍結保管，配合調查才袂有代誌。",
                "delay_ms": 3000,
            },
            {
                "speaker": "☎ 假檢警",
                "text": "這件代誌千萬袂使共別人講，連你孫仔嘛袂使講，電話不要掛斷，你這馬就去銀行匯錢，我會佇線頂陪你。",
                "delay_ms": 3000,
            },
        ],
    },
    {
        "id": "normal_grandson",
        "category": "正常通話",
        "title": "播孫子問候電話（溫馨關心）",
        "description": "孫子阿明打電話問候阿嬤吃飯沒，提醒這週末要回家煮苦瓜湯，並寄了牛奶提醒阿公按時吃藥。",
        "risk_level": "safe",
        "turns": [
            {
                "speaker": "👦 孫子阿明",
                "text": "阿嬤，我是阿明啦，呷飽未？我這禮拜六轉去看你，欲煮你上愛呷的苦瓜湯。",
                "delay_ms": 2500,
            },
            {
                "speaker": "👦 孫子阿明",
                "text": "阿公的藥仔有按時呷無？我買一箱牛奶寄轉去，你免出門提，佇厝裡等就好。",
                "delay_ms": 2500,
            },
        ],
    },
    {
        "id": "fraud_guess_who",
        "category": "猜猜我是誰",
        "title": "猜猜我是誰 / 假親友借錢",
        "description": "冒充多年未見姪子或換號碼的孫子，宣稱車禍受傷急需匯款賠償。",
        "risk_level": "fraud",
        "turns": [
            {
                "speaker": "☎ 假親友",
                "text": "阿嬤！猜猜我是誰？我換新的LINE跟電話號碼了啦，你緊共我記起來！",
                "delay_ms": 2500,
            },
            {
                "speaker": "☎ 假親友",
                "text": "阿嬤，我今仔日佇外頭撞到別人的車，現在在醫院急需五萬箍醫藥費賠償，你先匯一筆錢借我應急好無？",
                "delay_ms": 3000,
            },
        ],
    },
    {
        "id": "fraud_investment",
        "category": "假投資",
        "title": "假投資理財飆股群組",
        "description": "佯稱知名投顧名師助理，鼓吹加入私密群組保證獲利、穩賺不賠。",
        "risk_level": "fraud",
        "turns": [
            {
                "speaker": "☎ 假理財專員",
                "text": "阿姨您好，我是投顧名師的助理，我們群組每天分享主力飆股，保證獲利翻倍！",
                "delay_ms": 2500,
            },
            {
                "speaker": "☎ 假理財專員",
                "text": "老師親自帶盤穩賺不賠，現在加入專案帳戶匯款，名額有限，這期跟上保證賺大錢！",
                "delay_ms": 3000,
            },
        ],
    },
]


class AntiscamWebHandler(BaseHTTPRequestHandler):
    """客廳守護看板專用 HTTP 請求處理器。"""

    server_version = "AntiscamGuardianWeb/2026.1"

    def __init__(
        self, *args: Any, static_dir: Path | None = None, **kwargs: Any
    ) -> None:
        self.static_dir = static_dir or (_CURRENT_DIR / "static")
        self._scorer = Scorer() if Scorer is not None else None
        self._notifier = Notifier()
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        """客製化日誌輸出，保持終端清潔。"""
        # 僅在非 200 或重要路由時輸出日誌，或簡短顯示
        sys.stderr.write(f"[Web Dashboard] {self.address_string()} - {format % args}\n")

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        """發送 JSON 回應。"""
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, content: str | bytes, status: int = HTTPStatus.OK) -> None:
        """發送 HTML 頁面。"""
        body = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """處理 CORS 預檢請求。"""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """處理 GET 請求。"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 根目錄或 index.html: 回傳看板前端
        if path in ("/", "/index.html"):
            index_path = self.static_dir / "index.html"
            if index_path.is_file():
                try:
                    content = index_path.read_text(encoding="utf-8")
                    self._send_html(content)
                    return
                except Exception as e:
                    self._send_json(
                        {"error": f"無法讀取看板檔案: {e}"},
                        status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
            else:
                self._send_json(
                    {"error": f"找不到看板靜態檔案: {index_path}"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return

        # 劇本列表
        if path == "/api/scenarios":
            self._send_json({"ok": True, "scenarios": DEFAULT_SCENARIOS})
            return

        # 健康檢查
        if path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "status": "healthy",
                    "service": "阿嬤的台語反詐守門員客廳看板",
                    "version": "2026.1",
                }
            )
            return

        # 靜態資源 (如有額外檔案)
        if path.startswith("/static/"):
            rel_path = path[len("/static/") :]
            file_path = (self.static_dir / rel_path).resolve()
            if file_path.is_file() and str(file_path).startswith(
                str(self.static_dir.resolve())
            ):
                content_type = "application/octet-stream"
                if file_path.suffix == ".html":
                    content_type = "text/html; charset=utf-8"
                elif file_path.suffix == ".css":
                    content_type = "text/css; charset=utf-8"
                elif file_path.suffix == ".js":
                    content_type = "application/javascript; charset=utf-8"
                elif file_path.suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                    content_type = f"image/{file_path.suffix.lstrip('.')}"

                try:
                    data = file_path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception as e:
                    self._send_json(
                        {"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR
                    )
                    return

        # 其他路徑 404
        self._send_json({"error": f"Not Found: {path}"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        """處理 POST 請求。"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/score":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length)
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as err:
                self._send_json(
                    {"ok": False, "error": f"無效的 JSON 請求格式: {err}"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            text = str(payload.get("text", "")).strip()
            question = (
                str(payload.get("question", "咱家的狗叫啥名？")).strip()
                or "咱家的狗叫啥名？"
            )

            # 評分
            if self._scorer is not None:
                score_result = self._scorer.score(text)
            else:
                score_result = ScoreResult(
                    score=0.0, label="safe", matched=[], reasons=["評分器降級"]
                )

            # 告警轉化
            alert = decide(score_result)

            # 通關密語反向驗證
            # 通關密語反向驗證
            passcode_info = get_passcode_prompt(score_result, question=question)
            # 若為高風險詐騙 (fraud) 但樣板非親友類，亦提供通關密語反向驗證備用資訊
            if not passcode_info.get("triggered") and (
                score_result.label in ("fraud", "danger") or score_result.score >= 0.8
            ):
                passcode_info = {
                    "triggered": True,
                    "question": question,
                    "prompt_ta": f"阿嬤莫慌！先問伊通關密語：『{question}』",
                    "prompt_zh": f"防詐密語提示：請長輩詢問對方「{question}」反向驗證身份",
                    "fraud_emergency": True,
                }

            # LINE 模擬推送
            line_log_record: dict[str, Any] | None = None
            if alert.level in ("warning", "danger") or score_result.label in (
                "suspicious",
                "fraud",
            ):
                try:
                    line_log_record = self._notifier.notify(alert)
                except Exception as ex:
                    line_log_record = {"error": str(ex), "mock": True}

            # 關鍵詞高亮清單
            highlight_kws = extract_highlight_keywords(text)

            # 整理回傳結果
            response_data: dict[str, Any] = {
                "ok": True,
                "text": text,
                "score": round(score_result.score, 4),
                "score_percent": int(round(score_result.score * 100)),
                "label": score_result.label,
                "matched": score_result.matched,
                "reasons": score_result.reasons,
                "highlight_keywords": highlight_kws,
                "alert": alert.to_dict(),
                "passcode": passcode_info,
                "line_alert": {
                    "notified": line_log_record is not None,
                    "recipient": "大兒子（手機: 0912-***-456）",
                    "level": alert.level,
                    "message_zh": alert.message_zh,
                    "message_ta": alert.message_ta,
                    "record": line_log_record,
                },
            }
            self._send_json(response_data)
            return

        self._send_json({"error": f"Not Found: {path}"}, status=HTTPStatus.NOT_FOUND)


def find_available_port(host: str, start_port: int, max_tries: int = 50) -> int:
    """尋找可用連接埠，若 start_port 被佔用則自動遞增。"""
    for port in range(start_port, start_port + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                return port
        except OSError:
            continue
    raise RuntimeError(
        f"在 {host} 嘗試了 {max_tries} 個連接埠（從 {start_port} 起）皆已被佔用。"
    )


def run_server(
    host: str = "127.0.0.1", port: int = 8080, auto_port: bool = True
) -> None:
    """啟動 HTTP 守護看板伺服器。"""
    static_dir = _CURRENT_DIR / "static"
    if not static_dir.exists():
        static_dir.mkdir(parents=True, exist_ok=True)

    actual_port = port
    if auto_port:
        actual_port = find_available_port(host, port)

    def handler_factory(*args: Any, **kwargs: Any) -> AntiscamWebHandler:
        return AntiscamWebHandler(*args, static_dir=static_dir, **kwargs)

    server = HTTPServer((host, actual_port), handler_factory)

    banner = f"""
======================================================================
🛡️  【阿嬤的台語反詐守門員】全螢幕客廳守護看板 Web 伺服器
======================================================================
📡 服務已啟動於: http://{host}:{actual_port}/
💡 請在客廳大螢幕或筆電瀏覽器開啟上述網址。
📺 支援按 F11 鍵進入全螢幕沉浸模式。
🛑 按 Ctrl + C 即可安全停止伺服器。
======================================================================
"""
    print(banner, flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Web Dashboard] 收到停止信號，伺服器優雅關閉中...", flush=True)
    finally:
        server.server_close()
        print("[Web Dashboard] 伺服器已安全停止。", flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令列參數。"""
    parser = argparse.ArgumentParser(
        description="阿嬤的台語反詐守門員 — 全螢幕客廳守護看板 Web 伺服器"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="綁定 IP 位址（預設: 127.0.0.1，若需跨區域網路展示可設為 0.0.0.0）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="伺服器連接埠（預設: 8080，若被佔用且開啟 auto-port 則自動切換）",
    )
    parser.add_argument(
        "--no-auto-port",
        action="store_true",
        help="停用自動連接埠尋找（若被佔用直接報錯退出）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """伺服器主入口。"""
    args = parse_args(argv)
    try:
        run_server(
            host=args.host,
            port=args.port,
            auto_port=not args.no_auto_port,
        )
        return 0
    except Exception as e:
        sys.stderr.write(f"[Web Dashboard Error] {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
