# v0.1 驗收紀錄

作者：Nio (Master) · 日期：2026-10-08 · 執行：Codex

## 本次交付範圍

將既有「writer＋兩位 reviewer」的任務流程轉成獨立 Python runtime，附 CLI、合成示範、選配 HTTP adapter、測試、流程圖、心智圖與技術棧中英文對照。原始研究材料留在本機，不修改或重新壓縮原始論文。

## 已執行驗證

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`

**21 項測試通過。** 測試用暫存目錄與 HTTP server 均於結束時清除／關閉。

涵蓋：

- 子程序端到端合成示範，兩輪修訂後通過。
- reviewer 真正並行；不接收其他 reviewer 結果或前輪 feedback。
- 稿件 hash、輪次及來源綁定；拒絕舊版 verdict。
- 單一 reviewer 否決不能被另一位通過掩蓋。
- 達上限保留 unresolved 與最後稿件；篇幅超標另標警告。
- source_quote 不存在時拒絕；feedback 歸屬不可由模型覆寫。
- 格式錯誤、adapter 逾時、後代程序清理、空白輸入與非法參數。
- 原文不变、既有 run 不覆寫、JSON 原子替換失敗保留前版。
- 本機假 HTTP server 驗證 writer、facts、argument 契約；非 JSON、截斷、無效引用、remote HTTP 與 redirect 拒絕。

HTTP 測試使用固定回應，**不是 LLM 推論或供應商相容性測試**。

## 獨立 reviewer

獨立 `portfolio_reviewer` 只讀審查 runtime 與測試，提出三個問題：

| 問題 | 修正 | 驗證 |
|---|---|---|
| issue 可以覆寫 reviewer 歸屬 | 由 orchestrator 最後指定 role | 冒充角色的回歸測試 |
| timeout 只終止直接子程序 | POSIX process group 清理 | 派生子程序不再寫出延遲產物 |
| 直接覆寫摘要可能損毀前版 | 同目錄暫存、fsync、replace | 模擬 replace 失敗仍保留原 JSON |

第二次只讀復核確認三項修正成立；另建議補 reviewer HTTP 分支與 redirect 測試，已加入。Reviewer 未自行跑測試，測試結果由主執行端取得。

## 歷史資料核對

`python3 runtime/audit.py` 在完整本機研究目錄執行，讀取原稿、壓縮稿、review log；不改寫歷史資料。

- 10 組檔案；527,432 → 334,820 字元。
- 逐條 issue：10 筆；舊彙總正文記成 9 筆。
- 02、08、10 的 review log 字數與現存檔案不一致。
- 02 有 carried-over reviewer verdict；現存檔案沒有歷史逐輪 hash，不能事後補認證。

`historical-audit.json` 是現存檔案與歷史紀錄的一致性核對，不是語意品質評分。GitHub 可攜版本不含完整論文，因此獨立 clone 可跑 runtime/tests/demo，但不能在缺少本機 papers 的情況下重算歷史核對。

## 未完成的品質驗證

- 沒有本次新 runtime 的真實模型執行結果。
- 沒有人工 gold set、跨領域測試、v1/v2 成對實驗或 guard ablation 結果。
- 沒有模型能力、成本或時延的比較結論。
- 原文內的指令以提示詞限制處理，尚未進行 adversarial prompt-injection benchmark。

下一步只驗證本專案的真實推論與品質，不同時開展其他作品。

## 2026-10-08 Claude adapter 增補

新增四項 CLI 邊界測試：既有角色正文與模型別名載入、驗證失敗不得產稿、缺少 structured output 拒絕、兩個 reviewer 角色映射。目前合計 **25 項通過**，新增測試皆使用 mock subprocess。真實 Claude 嘗試被 OAuth 401 阻擋，並非模型品質驗證通過。

## Codex 角色移植實測增補

依 Nio 澄清，角色規準由 Codex agents 執行，不依賴 Claude CLI。新增 handoff adapter 六項測試：原子回覆、逾時保留請求、禁止 slot 重用、身份欄位驗證、錯稿指紋拒絕、晚到回覆不得完成新 inbox；目前 **31 項測試通過**。另完成一篇實際 agent 壓縮：19,377→13,143 字元，1 輪雙 reviewer 通過。此實測與 mock 測試分開記錄，詳見 [完整實驗報告](experiments/2026-10-08-openai-harness.md)。

最終獨立 reviewer 核對報告、結果 JSON 與本機稿件，確認數據與指紋一致；依其意見釐清主線派工／程序轉接及角色指紋另行核對的責任，並補上兩項 handoff 回歸測試。
