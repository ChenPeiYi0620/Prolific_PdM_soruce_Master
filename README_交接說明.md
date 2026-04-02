# AQbox RUL 監控系統 - 交接說明文件

## 📋 專案概述

本專案是 AQbox 馬達狀態監控與 RUL（剩餘使用壽命）預測系統，通過實時收集馬達傳感器數據、進行 IPC 算法估測，並持續監控馬達健康狀況。

**核心功能：**
- 與 AQbox 裝置通訊，定期收集 FAST（快速）和 RUL（壽命預測）數據
- 使用 IPC（In-Power-Controller）算法估測馬達轉矩、轉速、功率和效率
- 實時繪製監控圖表，直觀展示馬達運行參數
- 自動保存數據為 Parquet 格式，便於後續分析

---

## 🗂️ 目錄結構

```
AQbox_NTU_RUL_pico/
├── main_threads.py                ← ⭐ 主程式（直接執行此檔案）
├── AQbox_Parameters.csv            ← ⭐ 參數設定檔（修改配置在這裡）
│
├── modules/                        ← 所有函式模組  
│   ├── command_485.py              ← 485 通訊協議處理
│   ├── Data_handle.py              ← 數據轉換（u16 ↔ SI 單位）
│   ├── Data_handle_in_IPC.py       ← IPC 演算法估測引擎
│   ├── Motor_global_vars.py        ← 參數加載器
│   ├── rul_features/               
│   │   └── rul_data_read.py        ← RUL 數據讀取
│   └── __init__.py
│
├── Update_data/                    ← 數據儲存資料夾
│   ├── FAST_data/
│   └── RUL_data/
│
├── .venv/                          ← Python 虛擬環境
└── test_folder/                    ← 測試文件存放位置
```

---

## 🚀 快速開始

### 1️⃣ 環境準備

**系統需求：**
- **Python 版本：** 3.12.6+ （建議使用 3.10 以上）
- **操作系統：** Windows 10/11（主要開發環境）
- **USB 連接：** AQbox 裝置通過 USB 連接

**安裝依賴套件：**

方法 A：一鍵安裝（推薦）
```bash
cd AQbox_NTU_RUL_pico
pip install -r requirements.txt
```

方法 B：手動安裝個別套件
```bash
pip install numpy>=1.24.0 pandas>=1.5.0 matplotlib>=3.7.0 pyserial>=3.5 schedule>=1.1.0 pyarrow>=12.0.0
```

**如果使用虛擬環境：**
```bash
# Windows
cd AQbox_NTU_RUL_pico
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# 然後安裝依賴
pip install -r requirements.txt
```

**依賴套件清單：**

| 套件名 | 版本 | 用途 |
|--------|------|------|
| `numpy` | ≥1.24.0 | 數值計算、陣列操作 |
| `pandas` | ≥1.5.0 | 數據讀寫、CSV 處理 |
| `matplotlib` | ≥3.7.0 | 實時監控圖表繪製 |
| `pyserial` | ≥3.5 | 馬達通訊（RS485） |
| `schedule` | ≥1.1.0 | 定時任務排程 |
| `pyarrow` | ≥12.0.0 | Parquet 數據格式 |

### 2️⃣ 配置參數

編輯 `AQbox_Parameters.csv`，根據馬達規格調整參數。
詳見 **[AQbox_Parameters_欄位說明.md](AQbox_Parameters_欄位說明.md)**

### 3️⃣ 運行主程式

```bash
python main_threads.py
```

程式會：
- 自動檢測並連接到 AQbox 裝置
- 開啟實時監控圖表
- 按配置週期收集數據（預設 FAST/RUL 各 5 秒）
- 保存數據至 `Update_data/` 資料夾

---

## 📊 數據流向

```
AQbox 硬體傳感器 (u16)
           ↓
   Data_handle.py (u16 → SI 轉換)
           ↓
   Data_handle_in_IPC.py (IPC 估測算法)
           ↓
  轉矩 / 轉速 / 功率 / 效率
           ↓
      ┌────┴────┐
      ↓         ↓
   終端顯示   監控圖表   Parquet 儲存
```

---

## 🔧 主要參數說明

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `Motor_Rs` | 12 Ω | 馬達繞組電阻 |
| `Motor_P` | 8 | 馬達磁極數 |
| `Base_Speed` | 3000 RPM | 馬達基底速度 |
| `Base_Torque` | 1 N·m | 馬達基底轉矩 |
| `FAST_period` | 5 s | FAST 數據採集周期 |
| `RUL_period` | 5 s | RUL 數據採集周期 |

更多參數詳見 **[AQbox_Parameters_欄位說明.md](AQbox_Parameters_欄位說明.md)**

---

## 📈 監控圖表功能

程式自動生成 3 個監控圖表：

1. **馬達參數監控**
   - 實時轉矩、轉速、功率、效率
   - 紅色虛線標示告警閾值

2. **傳感器數據監控**
   - 電壓 (V)、電流 (A)、轉矩 (Nm)
   - SI 單位直觀展示

3. **效率**
   - 馬達效率曲線

---

## 🐛 常見問題

### Q: 如何修改數據採集週期？
**A:** 編輯 `AQbox_Parameters.csv` 中的 `FAST_period` 和 `RUL_period` 欄位。

### Q: 數據儲存在哪裡？
**A:** 自動儲存在 `Update_data/` 資料夾：
- `FAST_data/` - 快速數據（Parquet 格式）
- `RUL_data/` - 壽命預測數據（Parquet 格式）

### Q: 為什麼無法連接到 AQbox？
**A:** 
- 檢查 USB 連接
- 驗證 COM 埠編號（程式會自動掃描）
- 確認 AQbox 驅動已安裝

### Q: 如何調試模式運行（不連接硬體）？
**A:** 編輯 `main_threads.py` 第 ~43 行，改為 `DEBUG = True`

---

## 📝 運行日誌

終端輸出示例：
```
[IPC] torque=15.23 Nm, power(E)=2.342 kW, power(M)=2.198 kW, speed=2850 RPM, eff=93.8%
[FAST] 數據已保存: Update_data/FAST_data/...
[RUL] 數據已保存: Update_data/RUL_data/...
```

---

## 👤 技術支持聯繫人

如有問題，請參考：
1. 代碼中的中文註解（函式說明）
2. 函式索引（代碼開頭）
3. 本文件的 FAQ 部分

---

## � 系統需求

### 必要環境

**硬體：**
- CPU：雙核以上
- 記憶體：4 GB 以上
- 儲存：500 MB 以上可用空間

**軟體：**
- Python 3.12.6（或 3.10+）
- pip 26.0.1+
- Windows 10/11（或 macOS/Linux）

### Python 版本相容性

| Python 版本 | 相容性 | 備註 |
|-------------|--------|------|
| 3.12.6 | ✅ 完全相容 | 推薦（當前版本） |
| 3.11.x | ✅ 完全相容 | 會驗證 |
| 3.10.x | ✅ 完全相容 | 會驗證 |
| 3.9.x | ⚠️ 部分相容 | 可能需要調整 |
| 3.8.x 以下 | ❌ 不相容 | 不支援 |

### 依賴套件版本

詳見根目錄 `requirements.txt`：

```txt
numpy>=1.24.0
pandas>=1.5.0
matplotlib>=3.7.0
pyserial>=3.5
schedule>=1.1.0
pyarrow>=12.0.0
```

---

## �📌 版本歷史

- **v1.0** (2026-03-30) - 初始交接版本
  - IPC 演算法集成
  - 實時監控界面
  - Parquet 數據存儲

---

**最後修改日期：2026 年 3 月 30 日**
