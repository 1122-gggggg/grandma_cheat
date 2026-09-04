# 筆電部署 Ollama＋Gemma-TAIDE 指引 — 阿嬤的台語反詐守門員

2026 全國 AI 專題創意競賽・跨領域組｜本文件可直接列印，照著打指令即可
原則：Ollama 只是「可選加分」，沒裝、沒連上，`fraud` demo 照跑（關鍵詞降級）

---

## 1. 前置確認（30 秒）

- [ ] 筆電 OS：Windows 10/11、macOS、Ubuntu 皆可
- [ ] 硬碟剩餘 ≥ 10 GB（TAIDE 模型約 4～5 GB）
- [ ] 不需 GPU，CPU 即可跑；不需要網路（裝完模型後全程可斷網）
- [ ] 全程未使用任何中資模型／套件：只用 Ollama＋TAIDE 系列＋自寫規則

## 2. 安裝 Ollama（只做一次）

Windows / macOS：到 `https://ollama.com` 下載安裝檔，下一步到底。

Ubuntu 筆電：

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version
```

## 3. 下載 TAIDE 模型（擇一，有網路時先抓）

```bash
# 選項 A（優先）：Gemma3 TAIDE 版
ollama pull gemma3:taide

# 選項 B（備選）：Llama3.1 TAIDE 版
ollama pull llama3.1:taide
```

> 本專案 `Scorer` 預設送出的模型名是 `gemma-taide`（見
> `src/antiscam/brain/scorer.py` 的 `_OLLAMA_MODEL`）。為讓兩邊對上，
> 抓完後打一道別名即可，任選其一：
>
> ```bash
> ollama cp gemma3:taide gemma-taide
> # 或
> ollama cp llama3.1:taide gemma-taide
> ollama list
> ```
>
> 之後程式不用改，`Scorer().score("…")` 會自動找到本機模型。

## 4. 啟動服務＋連通測試（決賽當天早上做一次）

```bash
# 終端機一：啟服務（平常 Ollama 已常駐的話可略過）
ollama serve

# 終端機二：列模型＋打一次 /api/generate
ollama list
curl http://localhost:11434/api/generate -d '{
  "model": "gemma-taide",
  "prompt": "你是阿嬤的台語反詐守門員，只回一行「分數：0.x」。通話文字：我是地檢署檢察官，你涉及洗錢，要匯到監管帳戶。",
  "stream": false
}'
```

成功標誌：curl 回 `{"response": "…分數…", …}` 即連通。
失敗也沒關係：直接斷網跑 demo，見第 6 節。

## 5. Scorer 自動偵測邏輯（評審問就唸這段）

`Scorer().score(text)` 流程（`src/antiscam/brain/scorer.py`）：

1. 先算關鍵詞加權總和（clip 到 0～1），轉標籤：`<0.4` 安全、`＜0.8` 可疑、`≥0.8` 詐騙；
2. 再試一次 Ollama 二次確認（`POST {ollama_url}/api/generate`，timeout 2.0 秒，只試一次，不重試）；
3. LLM 只能把「可疑」往上確認為詐騙（`llm_score ≥ 0.8` 且標籤為 `suspect` 時升級為 `fraud`），不可推翻關鍵詞的 `fraud`／`safe`，避免誤擋阿嬤日常聊天；
4. 遇到以下任一情況一律靜默降級，回 `(None, "")`，不丟例外：沒裝 Ollama、沒跑 `ollama serve`、模型名對不上、斷網、回覆解析不出分數。此時 `reasons` 維持關鍵詞命中說明，分數就是關鍵詞分數。

## 6. 連不上降級的證據句（斷網聲明用）

決賽現場直接唸這一句，評審可當場驗證：

> 「本 demo 全程離線運行：沒裝 Ollama 或連不上 `localhost:11434` 時，
> `Scorer` 自動降級為關鍵詞規則，`reasons` 內沒有『Gemma-TAIDE』字樣即為證據；
> `uv run python -m antiscam.demo.runner --mode fraud` 三段假檢警照樣綠→黃→紅，
> 告警只寫本地 log，未送任何網路。」

驗證法（任一即可）：

```bash
# 法一：關掉 Ollama 再跑，照樣紅燈
# 先停掉 ollama serve，Wi-Fi 也可直接關掉
uv run python -m antiscam.demo.runner --mode fraud
# 預期：紅字大字報「疑似詐騙！緊掛電話！」正常出現

# 法二：看 reasons 有無 LLM 字樣（python 一行）
uv run python -c "from antiscam.brain.scorer import Scorer; r=Scorer().score('我是地檢署的，你涉及洗錢'); print(r.score, r.label, r.reasons)"
# 沒連 Ollama 時 reasons 只有「命中…」或「沒有命中…」，無 Gemma-TAIDE 字樣＝降級證據
```

## 7. 常見狀況排除

| 狀況 | 解法 |
|------|------|
| `ollama: command not found` | 重開終端機；Windows 重開機後再打 `ollama --version` |
| `pull` 卡住 | 換手機熱點或學校網路抓完再斷網；模型只需抓一次 |
| `Error: model 'gemma-taide' not found` | 補打第 3 節的 `ollama cp … gemma-taide` 別名 |
| 筆電跑 LLM 很慢 | 正常。`Scorer` timeout 僅 2 秒，逾時自動降級，demo 不會卡住 |
| 決賽現場沒網路 | 本來就不用網路。照第 6 節法一跑，評審反而更信服 |

---

## 附錄：Jetson Orin Nano 量化 Q4 指引（書面規劃，不需實機）

> 本段為書審／決賽 Q&A 備答用，隊上無 Jetson 實機也可講。核心一句話：
> 「筆電 CPU 跑關鍵詞版已可決賽；Jetson 只是未來駐點版的省電選項。」

- 目標機：Jetson Orin Nano 8 GB，JetPack 6，電源 5V⎓4A。
- 模型選量化版（擇一，8 GB 記憶體才塞得下）：
  ```bash
  ollama pull gemma3:taide-q4_K_M
  ollama cp gemma3:taide-q4_K_M gemma-taide
  # 或 llama3.1:taide-q4_K_M 同理
  ```
- 為何 Q4：Q4_K_M 約省一半記憶體，詐騙二分類對量化不敏感（Scorer 只取 0～1 分數，且只用來把 `suspect` 升級為 `fraud`，關鍵詞已先擋第一線），掉點可接受。
- 跑法不變：`ollama serve`＋`Scorer().score()` 同一套碼；Jetson 上把 `timeout` 從 2.0 秒放寬到 5 秒即可（CPU 較慢，寧可逾時降級也不卡住）。
- 借不到 Jetson 的備案：決賽就用筆電全離線 demo，本段只放書審「未來擴充」一節，不影響現場成績。
- 未使用任何中資模型／鏡像：Ollama 官網＋TAIDE 公開權重，來源寫進書審文件即可。
