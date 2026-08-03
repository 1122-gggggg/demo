# 中央場域語意定位展示

## Windows 執行
```powershell
git clone https://github.com/1122-gggggg/demo.git
cd demo
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

之後直接開啟介面：

```powershell
.\.venv\Scripts\python.exe show.py
```

## 操作

- 左鍵雙擊：切換地圖中心
- 右鍵拖曳：平移地圖
- 滾輪：縮放地圖

## 專案結構

```text
show.py                         # 唯一入口
run_windows.ps1                 # 建立環境、下載資料、啟動
中央展示介面.py                 # 介面、影片、點雲互動
展示核心.py                     # 資料路徑與核心邏輯
requirements.txt                # Python 套件
展示資產.sha256                 # 必要展示資料雜湊
scripts/download_demo_assets.py # 下載展示資料
```
