# Momo MVP

Momo 是一個單機互動裝置 MVP：用 webcam 追蹤觀眾，透過 Ollama 生成文本，交給 Qwen3-TTS voice clone 朗讀，再透過 ESP32 控制雙眼 SG90 伺服馬達。

## 架構

- `backend/`: Python 長駐程式，負責狀態機、prompt、Ollama、TTS、serial、telemetry。
- `frontend/`: Vite + TypeScript 控制台，調參、監看 pipeline、記憶體、servo 角度。
- `esp32/sg90/`: Arduino firmware，接收左右眼角度。
- `resource/`: system prompt、examples、voice clone 素材。

## 視覺與控制規則

- `YOLO11n` 用於 `person bbox` 與 threshold。
- 馬達追視優先看 face/eye tracking；若眼睛失效，回退到 person center。
- person bbox 決定 lock/unlock，眼睛定位只決定 servo aiming。
- Track mode LLM 依句序 `1..10` 對齊對應 example stage。
- UI 高亮顯示當前流程：`LLM > TTS > PLAYBACK`。

## 安裝

### Python

```bash
uv sync
```

### Node

前端固定使用 Node 22。

```bash
source ~/.nvm/nvm.sh
nvm install 22
nvm use 22
```

macOS Apple Silicon:
- 建議安裝對應 MPS 版 PyTorch。

Windows + NVIDIA:
- 先確認 CUDA Toolkit 版本，再安裝對應 CUDA 版 PyTorch。

如要補齊完整 vision/TTS 執行依賴，可再加裝：
- `ultralytics`
- `opencv-python`
- `mediapipe`
- `qwen-tts`
- `torch`

### Frontend

```bash
cd frontend
npm install
```

### Ollama

```bash
ollama serve
ollama pull llama3.1
```

## 啟動

後端：

```bash
uv run uvicorn backend.app:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

ESP32:
- 用 Arduino IDE 開啟 [esp32/sg90/sg90.ino](/Users/ian/Desktop/work/job/momo/esp32/sg90/sg90.ino)
- 安裝 `ESP32Servo`
- 燒錄後把 serial port 填進 UI

## API

- `GET /api/status`
- `GET /api/config`
- `POST /api/config`
- `GET /api/cameras`
- `GET /api/serial/ports`
- `GET /api/ollama/models`
- `POST /api/control/recenter-servos`
- `POST /api/control/simulate-track`
- `POST /api/control/simulate-pipeline`

## 測試

```bash
uv run pytest
```

前端 build:

```bash
cd frontend
npm run build
```

## 注意

- 瀏覽器相機是目前建議路徑：由前端取得 camera 權限，持續把 JPEG frame 上傳到後端做 YOLO/face/eye tracking。
- 若要用 backend OpenCV 直接開相機，macOS 需要對啟動後端的終端或 IDE 單獨授權 Camera。
- Qwen TTS 在 Apple Silicon 目前預設走 CPU，比較穩但速度較慢。
- `GET /api/audio/devices` 會列出本機 output devices，UI 可直接切換播放輸出。
- 前端 production build 已在 Node 22 驗證通過；Node 25 不建議使用。
