import os
import re
import uuid
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from mcp.server.fastmcp import FastMCP

APP_NAME = "RIZZ AE"
DATA_DIR = Path(os.getenv("RIZZ_AE_DATA_DIR", "/data"))
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
MAX_UPLOAD_MB = int(os.getenv("RIZZ_AE_MAX_UPLOAD_MB", "2048"))
ACCESS_TOKEN = os.getenv("RIZZ_AE_ACCESS_TOKEN", "").strip()

for directory in (UPLOAD_DIR, EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=APP_NAME, version="1.0.0")
mcp = FastMCP("RIZZ AE")


def authorized(request: Request) -> bool:
    return bool(ACCESS_TOKEN) and request.headers.get("authorization", "") == f"Bearer {ACCESS_TOKEN}"


@app.middleware("http")
async def protect_routes(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    if not authorized(request):
        return JSONResponse({"detail": "Unauthorized. Send a valid Bearer token."}, status_code=401)
    return await call_next(request)


def locate(file_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9-]{36}", file_id):
        raise ValueError("Invalid file ID.")
    found = list(UPLOAD_DIR.glob(f"{file_id}.*")) + list(EXPORT_DIR.glob(f"{file_id}.*"))
    if not found:
        raise FileNotFoundError("File ID not found.")
    return found[0]


def ffmpeg(args: list[str]) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed on this server.")
    result = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True, text=True, timeout=3600
    )
    if result.returncode:
        raise RuntimeError((result.stderr or "FFmpeg failed")[-2500:])


def new_export(extension: str = ".mp4") -> Path:
    return EXPORT_DIR / f"{uuid.uuid4()}{extension}"


def media_info(path: Path) -> str:
    if not shutil.which("ffprobe"):
        raise RuntimeError("FFprobe is not installed.")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return result.stdout


@app.get("/", response_class=HTMLResponse)
async def home():
    return """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RIZZ AE</title><style>
body{font:16px Arial;background:#09090b;color:#eee;max-width:680px;margin:35px auto;padding:20px}
.card{background:#18181b;padding:22px;border-radius:16px}
input,button{width:100%;padding:13px;margin:9px 0;box-sizing:border-box}
button{background:#d7ff35;border:0;border-radius:9px;font-weight:bold}
small{color:#aaa}
</style></head><body><h1>RIZZ AE</h1><p>Claude MCP + FFmpeg cloud media tools</p>
<div class="card"><label>Access token</label><input id="token" type="password" placeholder="Paste server token">
<label>Choose video/audio</label><input id="file" type="file" accept="video/*,audio/*">
<button onclick="upload()">Upload media</button><p id="result"></p>
<small>Keep your token private. Uploaded files remain on the server until removed.</small></div>
<script>
async function upload(){
 const f=document.getElementById('file').files[0],t=document.getElementById('token').value,r=document.getElementById('result');
 if(!f||!t){r.textContent='Choose a file and enter your token.';return;}
 const d=new FormData();d.append('file',f);r.textContent='Uploading...';
 try{const x=await fetch('/upload',{method:'POST',headers:{Authorization:'Bearer '+t},body:d});
 const j=await x.json();r.textContent=x.ok?'Uploaded. File ID: '+j.file_id:'Error: '+(j.detail||x.status);}
 catch(e){r.textContent='Upload failed: '+e;}
}
</script></body></html>"""


@app.get("/health")
async def health():
    return {"ok": True, "app": APP_NAME, "ffmpeg_available": bool(shutil.which("ffmpeg"))}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "upload.bin").suffix[:12] or ".bin"
    destination = UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(413, f"File exceeds {MAX_UPLOAD_MB} MB limit.")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {"file_id": destination.stem, "filename": file.filename, "size_bytes": size}


@app.get("/download/{file_id}")
async def download(file_id: str):
    try:
        path = locate(file_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(404, str(error))
    return FileResponse(path, filename=path.name)


@mcp.tool()
def rizz_ae_status() -> dict:
    """Check RIZZ AE service and FFmpeg availability."""
    return {"service": APP_NAME, "ffmpeg_available": bool(shutil.which("ffmpeg")),
            "upload_limit_mb": MAX_UPLOAD_MB}


@mcp.tool()
def get_video_info(file_id: str) -> str:
    """Return media metadata as JSON for an uploaded file ID."""
    try:
        return media_info(locate(file_id))
    except Exception as error:
        return f"ERROR: {error}"


@mcp.tool()
def trim_video(file_id: str, start_seconds: float, duration_seconds: float) -> str:
    """Trim a media file. Time values are seconds. Returns an export file ID."""
    try:
        if start_seconds < 0 or duration_seconds <= 0:
            return "ERROR: Invalid trim values."
        source = locate(file_id)
        target = new_export()
        ffmpeg(["-ss", str(start_seconds), "-i", str(source), "-t", str(duration_seconds),
                "-c:v", "libx264", "-c:a", "aac", str(target)])
        return f"Export file ID: {target.stem}"
    except Exception as error:
        return f"ERROR: {error}"


@mcp.tool()
def resize_video(file_id: str, width: int, height: int) -> str:
    """Resize video to the requested even width and height. Returns an export file ID."""
    try:
        if width < 16 or height < 16 or width > 7680 or height > 4320 or width % 2 or height % 2:
            return "ERROR: Use even dimensions between 16 and 7680x4320."
        source = locate(file_id)
        target = new_export()
        ffmpeg(["-i", str(source), "-vf", f"scale={width}:{height}",
                "-c:v", "libx264", "-c:a", "aac", str(target)])
        return f"Export file ID: {target.stem}"
    except Exception as error:
        return f"ERROR: {error}"


@mcp.tool()
def extract_audio(file_id: str, format: str = "mp3") -> str:
    """Extract audio. Supported formats: mp3, wav, m4a. Returns an export file ID."""
    try:
        extension = format.lower()
        if extension not in ("mp3", "wav", "m4a"):
            return "ERROR: Format must be mp3, wav, or m4a."
        source = locate(file_id)
        target = new_export("." + extension)
        ffmpeg(["-i", str(source), "-vn", str(target)])
        return f"Export file ID: {target.stem}"
    except Exception as error:
        return f"ERROR: {error}"


@mcp.tool()
def add_text_overlay(file_id: str, text: str, x: int = 40, y: int = 40, font_size: int = 36) -> str:
    """Add a simple white text overlay to a video. Returns an export file ID."""
    try:
        safe_text = (text.replace("\\", "\\\\").replace(":", "\\:")
                     .replace("'", "\\'").replace("%", "\\%"))
        source = locate(file_id)
        target = new_export()
        filter_text = (f"drawtext=text='{safe_text}':x={x}:y={y}:"
                       f"fontsize={max(10, min(font_size, 160))}:fontcolor=white:"
                       "box=1:boxcolor=black@0.45:boxborderw=10")
        ffmpeg(["-i", str(source), "-vf", filter_text,
                "-c:v", "libx264", "-c:a", "aac", str(target)])
        return f"Export file ID: {target.stem}"
    except Exception as error:
        return f"ERROR: {error}"


@mcp.tool()
def normalize_audio(file_id: str) -> str:
    """Normalize audio loudness and return an MP3 export file ID."""
    try:
        source = locate(file_id)
        target = new_export(".mp3")
        ffmpeg(["-i", str(source), "-vn", "-af", "loudnorm", str(target)])
        return f"Export file ID: {target.stem}"
    except Exception as error:
        return f"ERROR: {error}"


@mcp.tool()
def change_speed(file_id: str, speed: float) -> str:
    """Change video speed. Speed must be between 0.25 and 4.0. Returns an export ID."""
    try:
        if not 0.25 <= speed <= 4.0:
            return "ERROR: Speed must be between 0.25 and 4.0."
        source = locate(file_id)
        target = new_export()
        ffmpeg(["-i", str(source), "-vf", f"setpts=PTS/{speed}",
                "-af", f"atempo={speed}", "-c:v", "libx264", "-c:a", "aac", str(target)])
        return f"Export file ID: {target.stem}"
    except Exception as error:
        return f"ERROR: {error}"


@mcp.tool()
def create_thumbnail(file_id: str, at_seconds: float = 1.0) -> str:
    """Create a JPG thumbnail from a video at the requested time in seconds."""
    try:
        source = locate(file_id)
        target = new_export(".jpg")
        ffmpeg(["-ss", str(max(0, at_seconds)), "-i", str(source), "-frames:v", "1", str(target)])
        return f"Export file ID: {target.stem}"
    except Exception as error:
        return f"ERROR: {error}"


app.mount("/mcp", mcp.streamable_http_app())
