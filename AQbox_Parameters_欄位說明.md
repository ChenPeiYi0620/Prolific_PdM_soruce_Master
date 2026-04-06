# AQbox_Parameters.csv 欄位詳細說明

## 📋 概述

`AQbox_Parameters.csv` 是本系統的唯一配置檔案，包含 **21 個參數**，涵蓋馬達規格、硬體設定、採集策略等。

**修改注意：**
- 直接編輯 CSV 檔案即可生效（程式運行時自動讀取）
- 建議用 Excel 或文本編輯器打開
- 參數值以逗號分隔，勿亂加空格

---

## 🔧 完整參數表

### 第 1-4 段：馬達規格參數

| # | 欄位名 | 當前值 | 單位 | 說明 | 調整建議 |
|---|--------|--------|------|------|---------|
| 1 | `Motor_Rs` | 12 | Ω | **馬達繞組電阻** - 電機銘牌或規格表取得 | ⚠️ 正確性影響 IPC 估測精度 |
| 2 | `Motor_LS` | 0.00906 | H | **馬達漏感** - 電機特性參數 | 若無法取得，保持預設 |
| 3 | `Motor_P` | 8 | - | **磁極對數** = 馬達極數 ÷ 2。如 16 極馬達 → P=8 | 直接影響轉速計算 |
| 4 | `Base_Speed` | 3000 | RPM | **馬達基底轉速** - 額定轉速或常工作轉速 | 根據馬達銘牌修改 |

### 第 5-9 段：馬達基礎值（Per-Unit Base 標準化）

| # | 欄位名 | 當前值 | 單位 | 說明 | 調整建議 |
|---|--------|--------|------|------|---------|
| 5 | `Base_Torque` | 1 | N·m | **基礎轉矩** - IPC 估測的參考值 | 通常設為額定轉矩 |
| 6 | `Base_Power` | 100 | W | **基礎功率** - IPC 估測的參考值 | 通常設為額定功率 |
| 7 | `Base_Current` | 3.3942 | A | **基礎電流** - IPC 估測的參考值 | 根據馬達銘牌 |
| 8 | `Base_Voltage` | 300 | V | **基礎電壓** - IPC 估測的參考值 | 直流母線電壓 |
| 9 | `Base_Flux` | 0.05 | Wb | **基礎磁鏈** - 馬達磁路特性參數 | 若無法取得，保持預設 |

### 第 10-12 段：信號處理參數

| # | 欄位名 | 當前值 | 單位/說明 | 說明 | 調整建議 |
|---|--------|--------|---------|------|---------|
| 10 | `cn_range_scale` | 0.05 | - | **信噪比縮放係數** - 數據濾波參數 | 0.01~0.1，默認 0.05 |
| 11 | `data_length` | 5000 | 樣本數 | **每次採集的數據點數** - 越多越精確，但傳輸所需時間越多 | 最多10000點/四通道 |
| 12 | `Max_tries` | 3 | 次 | **通訊重試次數** - 連接失敗時重試次數 | 1~5 |

### 第 13-15 段：時間控制參數

| # | 欄位名 | 當前值 | 單位 | 說明 | 調整建議 |
|---|--------|--------|------|------|---------|
| 13 | `Update_period` | 3 | 秒 | **監控圖表更新周期** | 1~10 秒 |
| 14 | `RUL_update_times` | 2 | - | **RUL 更新頻率** - 每採集 N 次 FAST 數據後更新一次 RUL | 1~5 |
| 15 | `V_measure_mode` | Vpwm_mode | - | **電壓測量模式** - 固定為 `Vpwm_mode` | 勿修改 |

### 第 16-18 段：數據存儲與週期

| # | 欄位名 | 當前值 | 說明 | 調整建議 |
|---|--------|--------|------|---------|
| 16 | `Record File Path` | test_folder | 資料夾名稱（在 Update_data/ 下） | 修改為自定義資料夾名 |
| 17 | `FAST_period` | 5 | **FAST 數據採集週期（秒）** | 2~10 秒，更短 → 更精細監控 |
| 18 | `RUL_period` | 5 | **RUL 數據採集週期（秒）** | 通常與 FAST_period 相同 |

### 第 19-21 段：測試與除野參數

| # | 欄位名 | 當前值 | 說明 | 調整建議 |
|---|--------|--------|------|---------|
| 19 | `Transmit_test_flag` | 0 | **通訊測試模式** (0=關閉, 1=開啟) | 正常運行保持為 0 |
| 20 | `collection_times` | 2 | **測試採集次數** | 測試模式下的採樣數，正常為 2 |
| 21 | `outlier_number` | 0 | **除野閾值** - 刪除電壓最不穩(THD最大的) outlier_number 個檔案 避免電壓塗撥或幻象不穩時汙染檔案  |

---

## ⚙️ 參數調整工作流

### 🎯 場景 1：新馬達集成

**第一步：收集馬達規格**
- 查看馬達銘牌或規格表
- 填入以下必要參數：
  ```csv
  Motor_Rs (Ω), Motor_P (磁極數), Base_Speed (RPM), Base_Torque (N·m), Base_Power (W)
  ```

**第二步：確認基礎值**
- 根據馬達額定容量設置 `Base_Current` 和 `Base_Voltage`
- 確認直流母線電壓與 `Base_Voltage` 一致

**第三步：測試校準**
- 設置 `FAST_period` 和 `RUL_period` = 5 秒
- 運行程式，觀察終端輸出的 IPC 估測值
- 若估測轉矩/功率明顯異常，調調 `Base_*` 參數

---

### 🎯 場景 2：優化採集精度

**提高精度的做法（會降低速度）：**
1. 增加 `data_length` → 2500 至 5000
2. 減少 `Update_period` → 1 至 2 秒
3. 降低 `cn_range_scale` → 0.02 至 0.03

**加快速度的做法（會降低精度）：**
1. 減少 `data_length` → 1500 至 1000
2. 增加 `Update_period` → 5 至 10 秒
3. 增加 `cn_range_scale` → 0.08 至 0.1

---

### 🎯 場景 3：除野異常值

**啟用除野機制：**
```csv
outlier_number=2    # 刪除超出 2σ（標準差）的數據
```

**禁用除野：**
```csv
outlier_number=0    # 保留所有數據
```

> **建議：** 初期設為 0，檢查是否有異常值；確認後設為 2～3

---

## 📊 最小可運行配置

若不確定參數值，可使用以下**最小可運行配置**：

```csv
Motor_Rs(Ohm),Motor_LS(H),Motor_P,Base_Speed(Rpm),Base_Torque(N),Base_Power(W),Base_Current(A),Base_Voltage(V),Base_Flux(Wb),cn_range_scale,data_length,Max_tries,Update_period,RUL_update_times,V_measure_mode,Record File Path,FAST_period,RUL_period,Transmit_test_flag,collection_times,outlier_number
10,0.01,8,3000,1,100,3.5,300,0.05,0.05,2000,3,5,2,Vpwm_mode,data,5,5,0,2,0
```

**說明：**
- 使用通用馬達近似參數
- 採集周期 5 秒（適中）
- 數據存儲至 `Update_data/data/` 資料夾

---

## 🔍 IPC 算法估測原理

系統通過以下公式估測馬達狀態：

$$
\text{轉矩} = K_t \times \frac{磁鏈 \times 電流}{Base\_Torque}
$$

$$
\text{轉速} = \frac{Back\_EMF}{K_e \times 磁鏈}
$$

$$
\text{效率} = \frac{Power\_Mechanical}{Power\_Electrical} \times 100\%
$$

> **參數影響：**
> - `Base_*` 值決定估測靈敏度
> - `Motor_Rs`, `Motor_P` 直接決定計算精度
> - 誤差通常在 ±5% 以內

---

## 📋 快速檢查清單

運行程式前，確認以下項目：

- [ ] `Motor_Rs` = 馬達繞組電阻（歐姆）
- [ ] `Motor_P` = 磁極對數 （不是極數）
- [ ] `Base_Speed` = 額定轉速 (RPM)
- [ ] `Base_Voltage` = 直流母線電壓 (V)
- [ ] `FAST_period` / `RUL_period` ≥ 2 秒
- [ ] `Record File Path` 已指定（建議 `data` 或 `test_folder`）
- [ ] CSV 檔案編碼為 **UTF-8 或 ASCII**（Excel 可能自動轉換）

---

## ⚠️ 常見修改錯誤

| 錯誤 | 原因 | 解決方案 |
|------|------|---------|
| "No module Motor_global_vars" | CSV 讀取失敗 | 確保 CSV 格式正確，無多餘空格 |
| IPC 估測轉矩為 0 或異常大 | `Base_Torque` 設置不當 | 校準 `Base_*` 參數与實際馬達規格 |
| 圖表不更新 | `Update_period` 過長 | 減少至 1～2 秒 |
| 通訊頻繁中斷 | 採集速度過快 | 增加 `data_length` 或 `Update_period` |

---

## 📌 備註

- **CSV 檔案位置：** 根目錄 `AQbox_Parameters.csv`
- **讀取時機：** 程式啟動時讀取一次（修改後需重啟）
- **備份建議：** 修改前備份原始 CSV 檔案
- **版本控制：** 考慮在 git 中追蹤不同工況的 CSV 配置

---

**文件版本：v1.0 | 最後更新：2026-03-30**
