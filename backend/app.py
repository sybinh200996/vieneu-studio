import os
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.tts_engine import get_tts_engine, TTSEngine

# Cấu hình logging
logger = logging.getLogger("VieNeuApp")

# Khởi tạo FastAPI
app = FastAPI(
    title="VieNeu-TTS Studio API",
    description="Hệ thống tổng hợp và nhân bản giọng nói tiếng Việt VieNeu-TTS tối ưu cho CPU VPS",
    version="1.0.0"
)

# CORS Middleware cho phép mọi domain kết nối
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Định dạng âm thanh được hỗ trợ làm file mẫu Voice Cloning
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

@app.on_event("startup")
async def startup_event():
    logger.info("Ứng dụng VieNeu-TTS Studio đang khởi động...")
    # Kích hoạt singleton engine nạp model vào RAM
    engine = get_tts_engine()
    info = engine.get_info()
    logger.info(f"Trạng thái mô hình khởi động: {info['status']} | Model: {info['model_name']} | Precision: {info['precision']}")

@app.get("/api/health")
async def health_check():
    """Kiểm tra sức khỏe hệ thống và trạng thái nạp mô hình TTS"""
    engine = get_tts_engine()
    return {
        "app": "VieNeu-TTS Studio",
        "version": "1.0.0",
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
    text: str = Form(..., description="Văn bản tiếng Việt cần đọc"),
    voice: Optional[str] = Form("Hải Đăng", description="Tên giọng đọc dựng sẵn"),
    denoise: bool = Form(True, description="Tự động lọc tạp âm"),
    ref_audio: Optional[UploadFile] = File(None, description="File âm thanh mẫu 3-8 giây để nhân bản giọng")
):
    """
    Endpoint chính xử lý tổng hợp giọng nói:
    - Nếu không truyền ref_audio: Sử dụng giọng dựng sẵn (Preset Voice).
    - Nếu có ref_audio: Thực hiện Voice Cloning tức thì từ mẫu âm thanh tải lên hoặc thu trực tiếp.
    """
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Văn bản cần đọc không được để trống."
        )

    if len(clean_text) > 3000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Văn bản vượt quá giới hạn cho phép (tối đa 3000 ký tự trên phiên bản CPU)."
        )

    engine = get_tts_engine()
    temp_ref_path = None

    try:
        # Xử lý file âm thanh mẫu nếu người dùng chọn Voice Cloning
        if ref_audio is not None and ref_audio.filename:
            file_ext = Path(ref_audio.filename).suffix.lower()
            if not file_ext or file_ext not in ALLOWED_AUDIO_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Định dạng file không hỗ trợ: '{file_ext}'. Các định dạng hợp lệ: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
                )

            # Lưu file vào đĩa tạm
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp_file:
                temp_ref_path = tmp_file.name
                shutil.copyfileobj(ref_audio.file, tmp_file)

            # Kiểm tra kích thước file
            file_size = os.path.getsize(temp_ref_path)
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File âm thanh mẫu vượt quá 25MB."
                )

            if file_size < 1024:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File âm thanh mẫu quá ngắn hoặc rỗng. Vui lòng cung cấp đoạn âm thanh 3-8 giây."
                )

        # Gọi suy luận TTS
        wav_buffer = engine.infer(
            text=clean_text,
            voice=voice,
            ref_audio_path=temp_ref_path,
            denoise=denoise
        )

        return StreamingResponse(
            wav_buffer,
            media_type="audio/wav",
            headers={
                "Content-Disposition": 'attachment; filename="vieneu_speech.wav"',
                "Cache-Control": "no-cache",
                "X-Audio-SampleRate": str(engine.sample_rate)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xử lý TTS request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể tạo âm thanh: {str(e)}"
        )
    finally:
        # BẮT BUỘC: Xóa file âm thanh tạm thời sau khi xử lý xong để bảo vệ ổ cứng VPS
        if temp_ref_path and os.path.exists(temp_ref_path):
            try:
                os.remove(temp_ref_path)
                logger.info(f"Đã dọn dẹp file tạm thành công: {temp_ref_path}")
            except Exception as cleanup_err:
                logger.warning(f"Không thể xóa file tạm {temp_ref_path}: {cleanup_err}")

# Cấu hình phục vụ file tĩnh cho giao diện Frontend
current_dir = Path(__file__).resolve().parent
frontend_dir = current_dir.parent / "frontend"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info(f"Đã mount thư mục frontend tĩnh từ: {frontend_dir}")
else:
    logger.warning(f"Thư mục frontend chưa tồn tại tại: {frontend_dir}")
