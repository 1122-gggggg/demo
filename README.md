# 中央場域語意定位展示

這是可直接修改原始碼的 Windows 展示專案。它以已預算完成的 EDM + MegaLoc
位姿與語意揭露時序，重現雙串流、相機位姿、軌跡和累積染色的 3D 點雲介面。
不會連接真機，也不會發送飛行指令。

Git 只保存程式與說明；四個必要展示資產放在 GitHub Release，避免 clone 專案時
下載原始 4K 影片、PLY、定位模型或其他不影響回放的檔案。

## Windows 快速啟動

先安裝以下工具：

- [Git for Windows](https://git-scm.com/download/win)
- 64 位元 [Python 3.12](https://www.python.org/downloads/windows/)，安裝時勾選 **Add Python to PATH**。

在 PowerShell 執行：

```powershell
git clone https://github.com/1122-gggggg/demo.git
cd demo
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

第一次執行會建立 `.venv`、安裝 `requirements.txt`，並從本 repo 的最新 Release
下載約 290 MB 的最小展示資料。下載器會以 `展示資產.sha256` 驗證每個檔案；完成後
會直接開啟介面。之後只要在專案資料夾執行：

```powershell
.\.venv\Scripts\python.exe show.py
```

介面先停在原始點雲與串流首幀；按「開始自動巡檢」後才開始同步播放。

## 專案結構

| 檔案 | 責任 |
| --- | --- |
| `show.py` | 唯一入口與本機虛擬環境偵測。 |
| `中央展示介面.py` | Tk 介面、影片同步、點雲繪製與互動。 |
| `展示核心.py` | 路徑、回放資料契約與可單元測試的純函式。 |
| `scripts/download_demo_assets.py` | 從目前 GitHub remote 的最新 Release 下載並驗證資產。 |
| `run_windows.ps1` | 一次完成 Windows 環境建立、資產同步與啟動。 |
| `展示資產.sha256` | 唯一必要資產的 SHA-256 清單。 |

這些檔案就是可維護的中間架構；沒有額外框架或隱藏建置步驟。要調整版面、文字、
色彩、點雲互動或播放行為，從 `中央展示介面.py` 修改；要調整資料位置、回放速率或
語意顏色，從 `展示核心.py` 修改。

## 最小展示資產

最新版 Release 必須包含下列四個原始檔名，下載器會放回相對應路徑：

- `P1370137_demo_960x540.mp4`
- `P1370137_sam3_demo_960x540.mp4`
- `central_p1370137_poses.npz`
- `semantic_map.npz`

其中 `semantic_map.npz` 是完整 2,799,538 點地圖，`central_p1370137_poses.npz`
包含每個回放時刻的相機姿態與已觀測語意點時序。原始影片、原始/分割 PLY、EDM 模型
與重新預算定位的程式不屬於這個最小回放 repo。

## 修改後驗證

在已建立的環境中執行：

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

測試覆蓋回放時間映射、累積語意保留、顯示色盤、相機視錐、互動 LOD 與雙擊旋轉中心。
若你替換回放資料，請維持既有 NPZ 欄位與 `semantic_map.npz` 的點數一致，否則介面會在
啟動時明確提示資料契約不符。
