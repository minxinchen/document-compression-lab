# Runtime protocol｜執行資料契約

作者：Nio (Master) · 版本：compression-v1

支援 macOS／Linux（POSIX 程序群組）。在專案根目錄執行；command 內相對路徑以啟動時的工作目錄解析。核心僅使用 Python 標準函式庫。

## Request｜任務輸入

每次呼叫可信任的 adapter：stdin 接收一個 JSON，stdout 必須只輸出一個 JSON。不要在 stdout 印除錯訊息。

共同欄位：`protocol`、`role`（writer／facts／argument）、`iteration`、`source`、`source_sha256`、`target`、`tolerance`。

- Writer 額外取得 `previous_draft` 和 `feedback`，第一輪分別為 null 與空陣列。
- Reviewer 額外取得 `draft` 和 `draft_sha256`；不取得 writer 的自評或其他 reviewer 的結果。
- 字元數採 UTF-8 解碼後 Python `len()`，不正規化換行，含空白、標點及 metadata；不是 token 數。

## Response｜模型轉接器輸出

共同回傳 `protocol`、`role`、`iteration`、`source_sha256`，必須與請求完全相符。

Writer：另外回傳非空 `text`，包含完整稿件。

Reviewer：另外回傳 `draft_sha256`、`verdict`（pass／revise）和 `issues`。

```json
{
  "protocol": "compression-v1",
  "role": "facts",
  "iteration": 1,
  "source_sha256": "由請求取得的來源指紋",
  "draft_sha256": "由請求取得的稿件指紋",
  "verdict": "revise",
  "issues": [
    {
      "id": "F1",
      "problem": "刪掉測試期間，可能擴張結果適用範圍",
      "source_quote": "原文中實際存在的逐字片段",
      "suggestion": "補回測試期間及環境"
    }
  ]
}
```

pass 的 issues 必須為空；revise 至少有一筆。每筆需具備非空欄位，id 在同一 reviewer 當輪不可重複，source_quote 必須存在於 source。來源片段存在只證明可定位，不能證明 reviewer 的解釋正確。回饋歸屬以 orchestrator 指定的 role 為準，不接受 issue 自行冒充別的 reviewer。

## Status｜停止狀態

| Status | 中文意義 | CLI exit code |
|---|---|---|
| review_pass | 同一輪兩位 reviewer 都通過，篇幅達標 | 0 |
| review_pass_ratio_warning | 同版雙審查通過，篇幅未達標 | 3 |
| unresolved | 達迭代上限仍有修訂要求 | 2 |
| error | adapter、格式、綁定或其他執行錯誤 | 2 |

`review_pass` 只是兩位 reviewer 的一致判斷，不是人工金標準。無法由 hash 證明模型真的讀了全文，也不能用 hash 抵抗惡意 adapter。

## Artifacts｜執行證據

每次 run 要求新的輸出目錄。先保存原文快照，逐輪保存請求、回應、稿件與指紋。JSON 採同目錄暫存檔＋原子 replace，避免中斷時破壞上一份有效摘要；磁碟寫入失敗仍會回報錯誤，不保證故障磁碟上能留完整證據。

錯誤摘要不保存 exception 原文、stderr 或 API 回應 dump，以免將環境憑證寫入紀錄。內容產物仍可能含原文中的私密資料；`runs/` 不進 Git。

子程序使用獨立 POSIX process group，逾時／中斷／完成後清理同群組的後代。adapter 必須不 daemonize、不逃逸群組；這不是安全沙箱，必須只執行可信任命令。沒有自動重试，避免不知情重複付費；失敗後檢查紀錄並建立新 run。

## API adapter 限制

`http_adapter.py` 使用 stateless Chat Completions，將回應绑定至當次請求；writer 與兩位 reviewer 的 model ID 分開設定。只能從模型回覆解析 JSON 內容，`finish_reason` 必須是 `stop`；超出 context window 或截斷不得視為成功。API token 僅從環境讀取，禁止 URL 內嵌憑證或跟隨 redirect。

三個角色的 prompt 內建於 adapter，版本為 `compression-portable-v1`，這是工程化後的新提示詞，不等於歷史 Claude compressor v2。當前不提供分塊壓縮、斷點續跑、人工評分或 ablation runner。
