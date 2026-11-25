import os
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from starlette.concurrency import run_in_threadpool
from backend.tts_engine import get_tts_engine, TTSEngine, CPUQueueFullError, ModelNotReadyError
from backend.auth import (
    verify_admin_login,
    verify_admin_token,
    revoke_admin_token,
    create_api_key,
    list_api_keys,
    toggle_api_key,
    delete_api_key,
    validate_api_key
)
from backend.system_metrics import get_system_metrics

# Cấu hình logging
logger = logging.getLogger("VieNeuApp")

# Khởi tạo FastAPI
app = FastAPI(
    title="VieNeu-TTS Studio & Admin API",
    description="Hệ thống tổng hợp giọng nói tiếng Việt VieNeu-TTS tối ưu cho CPU VPS kèm Trang quản trị & API Keys",
    version="1.1.0"
)

# CORS Middleware cho phép mọi domain kết nối API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

current_dir = Path(__file__).resolve().parent
frontend_dir = current_dir.parent / "frontend"

@app.on_event("startup")
async def startup_event():
    logger.info("VieNeu-TTS Studio Server đang khởi động...")
    engine = get_tts_engine()
    info = engine.get_info()
    logger.info(f"Model status: {info['status']} | Model: {info['model_name']} | Voices: {info.get('total_voices', 0)}")

# --- PUBLIC ENDPOINTS ---

@app.get("/api/health")
async def health_check():
    """Kiểm tra sức khỏe hệ thống và trạng thái nạp mô hình TTS"""
    engine = get_tts_engine()
    return {
        "app": "VieNeu-TTS Studio",
        "version": "1.1.0",
        "engine": engine.get_info()
    }

@app.get("/api/voices")
async def get_voices():
    """Trả về danh sách 25 giọng đọc chuẩn 3 miền và các thẻ cảm xúc hỗ trợ"""
    engine = get_tts_engine()
    return {
        "voices": engine.voices_list,
        "emotion_tags": TTSEngine.SUPPORTED_TAGS
    }

@app.post("/api/tts")
async def synthesize_speech(
    request: Request,
    text: str = Form(..., description="Văn bản tiếng Việt cần đọc"),
    voice: Optional[str] = Form("Hải Đăng", description="Tên giọng đọc"),
    denoise: bool = Form(True, description="Tự động lọc tạp âm"),
    ref_audio: Optional[UploadFile] = File(None, description="File âm thanh mẫu Voice Cloning"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None)
):
    """
    Endpoint chính xử lý tổng hợp giọng nói:
    - Nếu có X-API-Key hoặc Authorization Bearer key: Xác thực key cho các website ngoài.
    - Nếu gọi trực tiếp từ Web Studio: Cho phép sử dụng tự do.
    """
    # Kiểm tra xác thực API key nếu request gửi từ bên ngoài có truyền key
    api_key_candidate = x_api_key
    if not api_key_candidate and authorization and authorization.startswith("Bearer vne_"):
        api_key_candidate = authorization

    if api_key_candidate:
        if not validate_api_key(api_key_candidate):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key không hợp lệ hoặc đã bị vô hiệu hóa trong Trang quản trị."
            )

    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Văn bản cần đọc không được để trống."
        )

    if len(clean_text) > 3000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Văn bản vượt quá giới hạn 3000 ký tự."
        )

    engine = get_tts_engine()
    temp_ref_path = None

    try:
        if ref_audio is not None and ref_audio.filename:
            file_ext = Path(ref_audio.filename).suffix.lower()
            if not file_ext or file_ext not in ALLOWED_AUDIO_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Định dạng file không hỗ trợ: '{file_ext}'"
                )

            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp_file:
                temp_ref_path = tmp_file.name
                shutil.copyfileobj(ref_audio.file, tmp_file)

            file_size = os.path.getsize(temp_ref_path)
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File âm thanh mẫu vượt quá 25MB."
                )

        wav_buffer = await run_in_threadpool(
            engine.infer,
            text=clean_text,
            voice=voice,
            ref_audio_path=temp_ref_path,
            denoise=denoise
        )

        return StreamingResponse(
            wav_buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'attachment; filename="speech.wav"',
                "Cache-Control": "no-cache"
            }
        )

    except CPUQueueFullError as e:
        logger.warning(f"Chống tràn hàng đợi CPU (429 Too Many Requests): {e}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
            headers={"Retry-After": "2"}
        )
    except ModelNotReadyError as e:
        logger.error(f"Mô hình TTS chưa sẵn sàng (503 Service Unavailable): {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi TTS: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi tạo giọng nói: {str(e)}"
        )
    finally:
        if temp_ref_path and os.path.exists(temp_ref_path):
            try:
                os.remove(temp_ref_path)
            except Exception:
                pass

# --- ADMIN API ENDPOINTS ---

class LoginPayload(BaseModel):
    username: str
    password: str

class CreateKeyPayload(BaseModel):
    name: str

def require_admin(authorization: Optional[str] = Header(None)) -> str:
    """Dependency kiểm tra quyền Admin qua Token"""
    username = verify_admin_token(authorization)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại."
        )
    return username

@app.post("/api/admin/login")
async def admin_login(payload: LoginPayload):
    """Đăng nhập quản trị với sybinh / dangnam và mật khẩu 200996 / 241204"""
    token = verify_admin_login(payload.username, payload.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác."
        )
    return {
        "success": True,
        "token": token,
        "username": payload.username.strip().lower()
    }

@app.post("/api/admin/logout")
async def admin_logout(authorization: Optional[str] = Header(None)):
    revoke_admin_token(authorization)
    return {"success": True}

@app.get("/api/admin/metrics")
async def get_metrics(admin_user: str = Header(None, alias="Authorization")):
    """Lấy dữ liệu thời gian thực về CPU, RAM, Disk của VPS và tiến trình TTS"""
    require_admin(admin_user)
    return get_system_metrics()

@app.get("/api/admin/keys")
async def get_keys(admin_user: str = Header(None, alias="Authorization")):
    """Lấy danh sách tất cả API Keys kết nối website khác"""
    require_admin(admin_user)
    return {"keys": list_api_keys()}

@app.post("/api/admin/keys")
async def create_new_key(payload: CreateKeyPayload, admin_user: str = Header(None, alias="Authorization")):
    """Tạo API key mới"""
    require_admin(admin_user)
    new_key = create_api_key(payload.name)
    return {"success": True, "key": new_key}

@app.put("/api/admin/keys/{key_id}/toggle")
async def toggle_key_status(key_id: int, admin_user: str = Header(None, alias="Authorization")):
    """Bật/tắt trạng thái API key"""
    require_admin(admin_user)
    success = toggle_api_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy API Key")
    return {"success": True}

@app.delete("/api/admin/keys/{key_id}")
async def remove_key(key_id: int, admin_user: str = Header(None, alias="Authorization")):
    """Xóa API key"""
    require_admin(admin_user)
    success = delete_api_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy API Key")
    return {"success": True}

# --- SERVE FRONTEND & ADMIN PAGE ---

@app.get("/admin")
async def serve_admin_page():
    admin_html = frontend_dir / "admin.html"
    if admin_html.exists():
        return FileResponse(str(admin_html))
    raise HTTPException(status_code=404, detail="Trang admin chưa sẵn sàng.")

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
