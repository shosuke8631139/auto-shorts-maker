"""
スマホ対応 動画自動編集サーバー
起動: python app.py
アクセス: http://<PCのIPアドレス>:8000
"""

import shutil
import socket
import uuid
from pathlib import Path
from threading import Thread

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

# ── ディレクトリ準備 ─────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
BGM_DIR = Path("bgm")
for d in (UPLOAD_DIR, OUTPUT_DIR, BGM_DIR):
    d.mkdir(exist_ok=True)

# ── ジョブ管理（メモリ内） ────────────────────────────────────
# {job_id: {status, message, output_path}}
jobs: dict[str, dict] = {}

app = FastAPI()


# ── BGM を bgm/ フォルダから探す ──────────────────────────────
def find_bgm() -> str | None:
    for ext in ("*.mp3", "*.wav", "*.aac", "*.m4a"):
        files = list(BGM_DIR.glob(ext))
        if files:
            return str(files[0])
    return None


# ── バックグラウンド処理 ──────────────────────────────────────
def run_job(job_id: str, input_path: str, output_path: str):
    from processor import process_video

    def on_status(msg: str):
        jobs[job_id]["message"] = msg

    try:
        bgm = find_bgm()
        process_video(input_path, output_path, bgm_path=bgm, on_status=on_status)
        jobs[job_id]["status"] = "done"
        jobs[job_id]["message"] = "完成！ダウンロードできます"
        jobs[job_id]["output_path"] = output_path
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = f"エラー: {e}"
    finally:
        Path(input_path).unlink(missing_ok=True)


# ── エンドポイント ────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/upload")
async def upload(file: UploadFile):
    job_id = uuid.uuid4().hex[:8]
    suffix = Path(file.filename).suffix.lower() or ".mp4"
    input_path = UPLOAD_DIR / f"{job_id}{suffix}"

    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    output_path = str(OUTPUT_DIR / f"{job_id}_output.mp4")
    jobs[job_id] = {"status": "processing", "message": "アップロード完了。処理を開始します...", "output_path": None}

    Thread(target=run_job, args=(job_id, str(input_path), output_path), daemon=True).start()
    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "ジョブが見つかりません")
    return jobs[job_id]


@app.get("/download/{job_id}")
async def download(job_id: str):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "動画がまだ完成していません")
    return FileResponse(
        job["output_path"],
        media_type="video/mp4",
        filename="completed_video.mp4",
    )


# ── モバイル対応 HTML（インライン） ───────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>動画自動編集</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f0f0f; color: #f0f0f0;
    min-height: 100vh; display: flex; flex-direction: column;
    align-items: center; padding: 32px 16px;
  }
  h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 8px; }
  .sub { color: #888; font-size: 0.85rem; margin-bottom: 32px; text-align: center; }

  .card {
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 16px;
    padding: 24px; width: 100%; max-width: 440px;
  }

  /* アップロードエリア */
  #drop-zone {
    border: 2px dashed #444; border-radius: 12px;
    padding: 40px 20px; text-align: center; cursor: pointer;
    transition: border-color .2s, background .2s;
    margin-bottom: 20px;
  }
  #drop-zone.dragover { border-color: #6cf; background: #1a2a3a; }
  #drop-zone .icon { font-size: 2.5rem; margin-bottom: 8px; }
  #drop-zone .label { font-size: 0.95rem; color: #aaa; }
  #drop-zone .filename { font-size: 0.9rem; color: #6cf; margin-top: 8px; font-weight: 600; }

  #file-input { display: none; }

  button {
    width: 100%; padding: 14px; border: none; border-radius: 10px;
    font-size: 1rem; font-weight: 700; cursor: pointer;
    transition: opacity .2s;
  }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  #upload-btn { background: #3a7cec; color: #fff; }
  #download-btn { background: #27ae60; color: #fff; margin-top: 12px; display: none; }

  /* 進捗エリア */
  #progress-area { margin-top: 20px; display: none; }
  .progress-bar-wrap {
    background: #2a2a2a; border-radius: 99px; height: 8px; overflow: hidden; margin-bottom: 10px;
  }
  .progress-bar {
    height: 100%; background: #3a7cec; border-radius: 99px;
    width: 0%; transition: width .4s;
    animation: pulse 1.5s ease-in-out infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
  .progress-bar.done { background: #27ae60; animation: none; width: 100% !important; }
  .progress-bar.error { background: #e74c3c; animation: none; }
  #status-msg { font-size: 0.9rem; color: #aaa; text-align: center; line-height: 1.5; }

  .tip {
    margin-top: 24px; padding: 14px; background: #111;
    border-radius: 10px; font-size: 0.8rem; color: #666; line-height: 1.7;
  }
  .tip strong { color: #888; }
</style>
</head>
<body>
<h1>🎬 動画自動編集</h1>
<p class="sub">動画をアップロードするだけで<br>字幕 + BGM を自動で追加します</p>

<div class="card">
  <div id="drop-zone" onclick="document.getElementById('file-input').click()">
    <div class="icon">📱</div>
    <div class="label">タップして動画を選択<br><small>MP4 / MOV 対応</small></div>
    <div class="filename" id="filename-display"></div>
  </div>
  <input type="file" id="file-input" accept="video/*">

  <button id="upload-btn" disabled onclick="startUpload()">アップロードして処理開始</button>

  <div id="progress-area">
    <div class="progress-bar-wrap">
      <div class="progress-bar" id="progress-bar"></div>
    </div>
    <div id="status-msg">処理中...</div>
  </div>

  <button id="download-btn" onclick="downloadVideo()">⬇️ 完成動画をダウンロード</button>
</div>

<div class="tip">
  <strong>💡 使い方</strong><br>
  1. iPhoneで撮影した動画を選ぶ<br>
  2. 「処理開始」をタップ<br>
  3. 完了したらダウンロード<br>
  <br>
  <strong>⏱ 処理時間の目安</strong><br>
  1分の動画 → 約2〜5分（初回はWhisperモデルのDLで追加数分）
</div>

<script>
let selectedFile = null;
let currentJobId = null;
let pollTimer = null;

const fileInput = document.getElementById('file-input');
const dropZone = document.getElementById('drop-zone');
const uploadBtn = document.getElementById('upload-btn');
const downloadBtn = document.getElementById('download-btn');
const progressArea = document.getElementById('progress-area');
const progressBar = document.getElementById('progress-bar');
const statusMsg = document.getElementById('status-msg');
const filenameDisplay = document.getElementById('filename-display');

// ファイル選択
fileInput.addEventListener('change', e => setFile(e.target.files[0]));
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => { e.preventDefault(); dropZone.classList.remove('dragover'); setFile(e.dataTransfer.files[0]); });

function setFile(file) {
  if (!file) return;
  selectedFile = file;
  filenameDisplay.textContent = file.name;
  uploadBtn.disabled = false;
}

// アップロード開始
async function startUpload() {
  if (!selectedFile) return;
  uploadBtn.disabled = true;
  downloadBtn.style.display = 'none';
  progressArea.style.display = 'block';
  progressBar.className = 'progress-bar';
  progressBar.style.width = '15%';
  statusMsg.textContent = 'アップロード中...';

  const formData = new FormData();
  formData.append('file', selectedFile);

  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const { job_id } = await res.json();
    currentJobId = job_id;
    progressBar.style.width = '30%';
    pollStatus();
  } catch (e) {
    showError('アップロードに失敗しました: ' + e.message);
  }
}

// ステータスポーリング
function pollStatus() {
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch('/status/' + currentJobId);
      const data = await res.json();
      statusMsg.textContent = data.message;

      if (data.status === 'done') {
        clearInterval(pollTimer);
        progressBar.className = 'progress-bar done';
        statusMsg.textContent = '✅ ' + data.message;
        downloadBtn.style.display = 'block';
        uploadBtn.disabled = false;
      } else if (data.status === 'error') {
        clearInterval(pollTimer);
        showError(data.message);
      } else {
        // アニメーション中は幅を少しずつ増やす演出
        const w = parseInt(progressBar.style.width) || 30;
        if (w < 90) progressBar.style.width = (w + 2) + '%';
      }
    } catch (e) { /* ネットワーク一時エラーは無視 */ }
  }, 3000);
}

function downloadVideo() {
  window.location.href = '/download/' + currentJobId;
}

function showError(msg) {
  progressBar.className = 'progress-bar error';
  progressBar.style.width = '100%';
  statusMsg.textContent = '❌ ' + msg;
  uploadBtn.disabled = false;
}
</script>
</body>
</html>
"""


# ── 起動 ─────────────────────────────────────────────────────
def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


if __name__ == "__main__":
    ip = get_local_ip()
    print("=" * 50)
    print("  動画自動編集サーバー 起動中")
    print(f"  PC から開く  : http://localhost:8000")
    print(f"  スマホから開く: http://{ip}:8000")
    print("  終了: Ctrl + C")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
