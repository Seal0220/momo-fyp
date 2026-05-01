# Momo Vision Backend

Momo 現在只保留 Python backend、人物偵測與 Arduino/ESP32 控制。後端預設由 Python/OpenCV 直接開啟 webcam 做 YOLO person detection，並透過 serial 將雙眼 SG90 servo 與 LED 亮度指令送到 ESP32。

## 架構

- `backend/`: FastAPI 長駐程式，負責 camera ingest、人物偵測、狀態機、servo/LED mapping、serial、telemetry。
- `backend/vision/`: YOLO person detection、bbox 中心點、距離、衣著顏色與身形分類。
- `backend/audio/states/`: 互動音效資料夾，使用 `no_one`、`left`、`center`、`right`、`full` 狀態放預錄音檔。
- `backend/serial/`: ESP32 serial link 與 compact JSON command。
- `backend/servo/`: 眼球 servo 幾何與角度計算。
- `esp32/`: Arduino firmware 與硬體測試 sketch。
- `tests/`: Python backend、vision、serial、servo 測試。

## 安裝

Windows 可直接執行：

```bat
install.bat
```

這會自動檢查 Python 3.11/3.12、安裝 `uv`，並執行 `uv sync --dev` 建立 `.venv` 與安裝專案依賴。

也可以手動執行：

```bash
uv sync
```

`uv sync` 會依作業系統安裝 PyTorch：

- macOS: `torch==2.4.1`、`torchvision==0.19.1`
- Windows: `torch==2.4.1+cu118`、`torchvision==0.19.1+cu118`

Python 建議使用 `3.11` 或 `3.12`。

## 啟動

```bash
uv run python -m backend.app --reload
```

預設 API 位址是 `http://127.0.0.1:8000`。若要改 host/port：

```bash
uv run python -m backend.app --host 0.0.0.0 --port 8000
```

可用 `MOMO_SKIP_MODEL_BOOTSTRAP=1` 跳過啟動時的 YOLO model 準備。

## 監控視窗

啟動後用瀏覽器開啟：

```text
http://127.0.0.1:8000/monitor
```

監控頁會顯示 Python 後端相機的標註畫面、人物 bbox、tracking mode、YOLO FPS、servo 角度、serial 狀態與最近事件。`Python Camera` 按鈕會把 camera source 切回後端 OpenCV capture。

注意：後端 OpenCV 只能讀取「執行 `backend.app` 那台電腦」本機作業系統看得到的 webcam。若瀏覽器測試可用但監控頁沒有畫面，先確認：

- 後端程式是否真的跑在插著 webcam 的那台電腦上。
- 瀏覽器測試頁、Teams、OBS 等程式是否還佔用著同一顆 webcam。
- Windows 設定中的 Camera privacy 是否允許 desktop apps 存取相機。
- 插上 webcam 後按監控頁的 `Refresh` / `Apply`，或等待後端自動重試。
- 若系統有很多虛擬相機，可用 `MOMO_CAMERA_SCAN_LIMIT=15` 增加 OpenCV 掃描 index 上限。

## Interaction Audio

人物偵測後會依畫面區域觸發 `no_one`、`left`、`center`、`right`、`full` 五種互動音效狀態。左右/中間可依 ROI 同時或獨立播放；`full` 代表單一人物佔滿畫面時的全畫面狀態。

請把預錄音檔放在：

```text
backend/audio/states/no_one/
backend/audio/states/left/
backend/audio/states/center/
backend/audio/states/right/
backend/audio/states/full/
```

支援的音檔副檔名包含 `.wav`、`.mp3`、`.m4a`、`.ogg`。後端會用 `ffmpeg` / `imageio-ffmpeg` 解碼音檔，套用 reverb、開頭淡入與結尾淡出後，再透過內建 Python mixer 播放；不再使用舊的 `far/mid/near` 位置音效資料夾。

## ESP32

1. 用 Arduino IDE 開啟 `esp32/sg90/sg90.ino`
2. 安裝 `ESP32Servo`
3. 燒錄後接上 USB serial
4. 後端預設 `serial_port=auto`，會優先選 USB/CH340/CP210/UART 類 serial 裝置

送出的 serial payload 是 compact JSON，例如：

```json
{"type":"servo","mode":"track","left_deg":100.24,"right_deg":80.1,"led_left_pct":72.5,"led_right_pct":27.5,"led_signal_loss_fade_out_ms":3000,"tracking_source":"person_center"}
```

## API

- `GET /api/health`
- `GET /` 或 `GET /monitor`
- `GET /api/status`
- `GET /api/config`
- `POST /api/config`
- `GET /api/cameras`
- `GET /api/camera/frame.jpg`
- `POST /api/camera/frame`
- `GET /api/serial/ports`
- `POST /api/control/recenter-servos`

`POST /api/camera/frame` 仍可接收 JPEG bytes。若 `camera_source` 是 `browser`，後端會在處理 frame 後立即送出 servo/LED tracking command；預設路徑則是 Python/OpenCV 後端相機。

## 測試

```bash
uv run pytest
```
