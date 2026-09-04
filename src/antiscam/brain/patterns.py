"""詐騙話術樣板：載入 JSON 並做關鍵詞子字串比對。

資料來源是跨組共用的 `data/fraud_patterns.json`。
缺檔或壞檔時 `load_patterns` 回傳空串列（不丟例外），
比對會自動改用內建保底樣板，讓斷網 demo 照常運作。
"""

import json


# 內建保底樣板：JSON 缺檔時啟用，欄位與共用契約一致。
# 權重設計：任兩個假檢警特徵同時出現（例如地檢署＋監管帳戶）必達 0.8 以上。
BUILTIN_PATTERNS: list[dict] = [
    {
        "id": "fake_police_office",
        "category": "假檢警",
        "keywords_zh": ["地檢署", "檢察官", "法院傳票"],
        "keywords_ta": ["kiám-chhat-koaⁿ", "檢察官"],
        "weight": 0.5,
        "example": "這裡是地檢署，你涉及刑案要配合調查。",
    },
    {
        "id": "fake_police_custody",
        "category": "假檢警",
        "keywords_zh": ["監管帳戶", "監管賬戶", "安全帳戶"],
        "keywords_ta": ["kam-tok tiùⁿ-hō͘", "監管帳戶"],
        "weight": 0.5,
        "example": "請把錢轉到監管帳戶接受調查，否則凍結帳戶。",
    },
    {
        "id": "fake_investment",
        "category": "假投資",
        "keywords_zh": ["保證獲利", "穩賺不賠", "投資群組", "老師報牌"],
        "keywords_ta": ["pó-chèng he̍k-lī", "保證獲利"],
        "weight": 0.6,
        "example": "加入投資群組保證獲利，穩賺不賠。",
    },
    {
        "id": "fake_family",
        "category": "假親友",
        "keywords_zh": ["猜猜我是誰", "換電話號碼", "先匯一筆錢"],
        "keywords_ta": ["io̍h-chhaiⁿ góa sī siáng", "猜猜我是誰"],
        "weight": 0.6,
        "example": "猜猜我是誰？我換電話號碼了，先匯一筆錢給我應急。",
    },
]


def _normalize(text: str) -> str:
    """正規化：轉小寫並移除所有空白，方便中英混雜比對。"""
    return "".join(text.lower().split())


def load_patterns(path: str = "data/fraud_patterns.json") -> list[dict]:
    """讀取詐騙樣板 JSON。

    缺檔、壞檔或格式不符時回傳空串列，不丟例外。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, OSError, ValueError, UnicodeDecodeError):
        return []
    return data if isinstance(data, list) else []


def match_keywords(
    text: str, patterns: list[dict] | None = None
) -> list[tuple[str, float]]:
    """用子字串比對找出命中的樣板，回傳 [(樣板 id, 權重)]。

    同一樣板有多個關鍵詞命中時只算一次（取該樣板權重）。
    `patterns` 省略時讀預設 JSON，缺檔則改用內建保底樣板。
    """
    if not isinstance(text, str) or not text.strip():
        return []
    if patterns is None:
        loaded: list[dict] = load_patterns()
        patterns = loaded if loaded else BUILTIN_PATTERNS
    norm_text: str = _normalize(text)
    if not norm_text:
        return []
    hits: list[tuple[str, float]] = []
    for p in patterns:
        if not isinstance(p, dict):
            continue
        pid: str = str(p.get("id", ""))
        try:
            weight: float = float(p.get("weight", 0.0))
        except (TypeError, ValueError):
            continue
        keywords: list[str] = list(p.get("keywords_zh", []) or []) + list(
            p.get("keywords_ta", []) or []
        )
        for kw in keywords:
            norm_kw: str = _normalize(str(kw))
            if norm_kw and norm_kw in norm_text:
                hits.append((pid, weight))
                break
    return hits
