# 工作交接紀錄 — 2026/04/01

## 已完成

### 1. LINE Bot + 市場日報
- `line_bot.py` — LINE Messaging API 整合（推播、Webhook、訂閱管理）
- `daily_report.py` — 每日市場日報產生器（三大指數、VIX、板塊、持倉警示）
- 排程：每天 07:30 台灣時間自動廣播（APScheduler）
- LINE Channel：何則興（Secret/Token 已設定在 Render 環境變數）
- 手動推播：網頁「市場日報」頁面可預覽 + 一鍵發送

### 2. 報價圖片產生器
- `quote_generator.py` — 填入參數自動抓收盤價產出 PNG 圖片
- 股價來源優先順序：資料庫 → yfinance → Finnhub → Yahoo API
- 網頁表單：`/quote`，支援自訂標的（手動輸入代號+中文名）
- 排版：淺粉色配色，已依使用者要求調整

### 3. 客戶文件產生器
- `ts_parser.py` — TS PDF 自動解析器（支援 DBS、SG 格式）
- `client_doc_generator.py` — 解析後產出客戶版簡易文件圖片
- 網頁上傳：`/upload_ts`

### 4. 雲端部署
- **Render**：https://fcnmanager.onrender.com（Free 方案）
- **Neon PostgreSQL**：`ep-bold-feather-a1agplsp-pooler.ap-southeast-1.aws.neon.tech/neondb`
- **GitHub**：`Jasper5511/FCNManager`（master 分支，Auto-Deploy）
- 字型：自動下載 Noto Sans TC → 轉靜態字型（`setup_fonts.py`）
- 資料已從本機 SQLite 搬移至 Neon

### 5. 客戶報告 PDF 改版
- 標題+摘要+持倉明細合併第一頁
- KO水準 → 提前出場價
- 移除「距Strike」欄位
- 標的加中文名稱
- 執行價旁顯示百分比
- 無 EKI 時隱藏該欄位
- 線圖兩張並排
- 免責聲明已移除

## 目前進度

| 功能 | 電腦 | 手機(Render) |
|------|------|-------------|
| 持倉總覽 | OK | OK |
| 報價產生 | OK | OK（股價從資料庫讀） |
| 客戶文件上傳 | OK | OK |
| 市場日報 | OK | OK |
| 客戶報告 PDF | OK（含線圖） | OK（無線圖） |
| 更新收盤價 | OK | 被 Yahoo 封鎖 |
| LINE 推播 | OK | OK |

## 未完成 / 已知問題

1. **Render 上無法抓 Yahoo 股價** — 雲端 IP 被封鎖，yfinance/Yahoo API 都不行。目前報價產生器改從資料庫讀取已更新的價格，需要使用者在電腦上先「更新收盤價」
2. **Render 客戶報告無線圖** — 同上原因，圖表抓不到歷史資料
3. **LINE Webhook 未設定** — LINE Developers Console 的 Messaging API 頁面找不到 Webhook URL 設定欄（可能介面改版）。不影響推播功能，只影響用戶在 LINE 上傳指令互動
4. **日報內容** — 使用者表示格式不是他喜歡的，需之後調整
5. **客戶報告分產品產出** — 使用者希望多商品時各自一份報告，不要擠在同一個檔案
6. **TS 解析器** — 目前只測過 DBS 和 SG 兩種格式，其他發行商（UBS、BNP、HSBC 等）第一次用可能需要修正

## 下一步

1. 客戶報告改為按商品分別產出
2. 日報內容格式調整（等使用者給範例）
3. 逐步累積各發行商 TS 格式支援
4. 考慮 Finnhub 免費 API Key 解決雲端股價問題（https://finnhub.io 註冊免費）
5. LINE Webhook 設定（等 LINE 介面更新或找替代方式）

## 注意事項

- **數據原則**：股價必須用前一完整交易日收盤，不用盤中即時價
- **KO 判定**：yfinance 與 Bloomberg 有誤差，KO 只標「疑似」由使用者確認
- **商品排序**：依 created_at 升序，新承作排最下面
- **檔案產出**：一律放桌面，不放子資料夾
- **數據來源**：直接用 TS 上的原始數字，不自行計算
- **Render 免費方案**：閒置 15 分鐘後休眠，喚醒需 30-50 秒
- **Neon 免費方案**：0.5GB 儲存，閒置後自動休眠，連線時自動喚醒
- **部署方式**：改程式碼 → git push → Render 自動部署（約 3-5 分鐘）

## 環境變數（Render）

| Key | 說明 |
|-----|------|
| FLASK_ENV | production |
| SECRET_KEY | 已設定 |
| LINE_CHANNEL_SECRET | 已設定 |
| LINE_CHANNEL_ACCESS_TOKEN | 已設定 |
| PYTHON_VERSION | 3.11.0 |
| DATABASE_URL | postgresql://...neon.tech/neondb?sslmode=require |

## 檔案結構

```
FCNManager/
├── app.py              # Flask 主程式（所有路由）
├── models.py           # 資料庫模型
├── config.py           # 環境設定
├── wsgi.py             # Gunicorn 入口
├── line_bot.py         # LINE Bot 模組
├── daily_report.py     # 市場日報產生器
├── quote_generator.py  # 報價圖片產生器
├── ts_parser.py        # TS PDF 解析器
├── client_doc_generator.py  # 客戶文件圖片產生器
├── setup_fonts.py      # 跨平台字型載入
├── requirements.txt    # Python 套件
├── Procfile            # Render 啟動指令
├── render.yaml         # Render 設定
├── runtime.txt         # Python 版本指定
├── templates/          # HTML 模板
│   ├── base.html
│   ├── dashboard.html
│   ├── quote.html
│   ├── upload_ts.html
│   ├── daily_report.html
│   ├── line_settings.html
│   └── ...
├── instance/           # 本機 SQLite（.gitignore）
└── fonts/              # 下載的字型（.gitignore）
```
