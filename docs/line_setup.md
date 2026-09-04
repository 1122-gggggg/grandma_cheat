# LINE 設定（5 分鐘）— 阿嬤的台語反詐守門員

平時用真推播通知囝仔，決賽（南大中山館）現場斷網自動切 mock，全程可跑。

## 三步建好 Channel

1. 建 Channel：開 [LINE Developers Console](https://developers.line.biz/) → 新增 Provider（如「阿嬤守門員」）→ Create a Messaging API channel → 填名稱、大頭貼、分類後建立。
2. 發 token：進該 Channel → Messaging API 分頁 → 最下方 Channel access token → Issue（長期有效那組）→ 立刻複製，只貼進環境變數，不寫進程式、不進 git。
3. 加好友取 ID：同一分頁掃 QR code 把機器人加為好友 → 用戶先傳一句「你好」→ 到 LINE Official Account Manager 或以 `GET /v2/bot/followers/ids` 查該用戶的 userId，即為 `LINE_TARGET_ID`（家人／測試機各一組）。

## 環境變數匯出

```bash
export LINE_CHANNEL_TOKEN="貼上剛發的長期 token"
export LINE_TARGET_ID="貼上家人或測試機的 userId"
uv run python -c "from antiscam.guardian.line_bot import LineBot; from antiscam.contracts import Alert; print(LineBot().push(Alert('warning','測試：疑似詐騙','疑似詐騙！緊掛電話！')))"
```

- 程式用法：`LineBot().push(alert)`，有 token 走真推播並回 `{"mode": "live", ...}`；無 token 或連線失敗回 `{"mode": "mock", "logged": ...}`，`logged` 那行就是投影要秀的本地 log。
- 安全：token 只讀環境變數，絕不寫死、不寫文件、不 commit；換電腦重 export 一次即可。

## 中山館斷網時切 mock 的判斷句

上場前看一行就好：`LineBot().push()` 回傳的 `mode` 是 `live` 還是 `mock`。

- `mode == "live"`：有網路有 token，真推播已送出。
- `mode == "mock"`：沒 token 或現場斷網，已自動降級寫本地 log，直接投影 `logged` 那行繼續講。

決賽話術（斷網時照唸）：「現場斷網，告警寫本地log，投影同一行」。

## 驗證（30 秒）

- 無 token：先 `unset LINE_CHANNEL_TOKEN` 再跑上面指令，應回 `mode: mock` 且 `runs/line_mock.log` 多一行，全程零網路呼叫。
- 有 token：export 後跑一次，應回 `mode: live` 且手機收到推播；失敗只打一次不重試，自動回 `mode: mock`，不會重試風暴。
