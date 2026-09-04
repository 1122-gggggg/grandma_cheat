# 阿嬤的台語反詐守門員 👵🛡️

2026 全國 AI 專題創意競賽・跨領域組 MVP

即時監聽電話 → 台語/華語辨識 → 詐騙關鍵詞 + LLM 評分 → 台語語音告警，
幫阿嬤擋下假檢警、假投資、假親友電話。

## 3 步啟動

### 1️⃣ 安裝（需連網一次）

```bash
uv sync
```

### 2️⃣ 跑 demo（評審現場用）

```bash
uv run demo
# 或：uv run python -m antiscam.demo.runner
```

demo 會播預錄詐騙電話範例 → 顯示辨識文字 → 詐騙評分 → 台語告警。
10 秒滑動窗口在 demo 層做，評分每 10 秒彙整一次。

### 3️⃣ 斷網說明（決賽 12/19 南大中山館，現場斷網可 demo）

- 比賽前先做步驟 1（`uv sync` 會把 faster-whisper 模型載到本機快取）。
- 決賽現場**不用連網**：語音辨識（faster-whisper 本地模型）+ 關鍵詞規則評分都在筆電 CPU 跑。
- Ollama（Gemma-TAIDE / Llama / Gemma / Phi）是**可選加分**：連得上就用 LLM 複核，
  連不上自動降級為關鍵詞規則，demo 不會炸掉。
- 全程禁中資模型：只用 faster-whisper / Whisper、Ollama 上述模型、關鍵詞規則。

## 跨領域分工表

| 組員 | 負責 | 產出檔案 |
|------|------|----------|
| 資電（Scaffold） | 專案骨架、共用契約、詐騙關鍵詞庫、本 README | `pyproject.toml`、`src/antiscam/contracts.py`、`data/fraud_patterns.json` |
| 音訊組 | 麥克風收音、語音轉文字 | `src/antiscam/audio.py`（`Transcriber.transcribe(wav_path)->list[Segment]`） |
| 腦組 | 關鍵詞 + Ollama 詐騙評分 | `src/antiscam/brain.py`（`Scorer.score(text)->ScoreResult`） |
| 守門組 | 台語告警、log、demo 呈現 | `src/antiscam/guardian.py`（`Notifier.notify(alert)->dict`，只寫 local log） |

共用契約（所有人照此寫）：`src/antiscam/contracts.py` 的
`Segment(text,start,end,lang)`、`ScoreResult(score,label,matched,reasons)`、
`Alert(level,message_zh,message_ta)`；10 秒滑動窗口在 demo 層做。
