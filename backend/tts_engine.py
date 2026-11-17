import io
import os
import logging
import threading
import tempfile
from typing import Optional, List, Dict, Any

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TTSEngine")

try:
    import numpy as np
except ImportError:
    np = None

try:
    import soundfile as sf
except ImportError:
    sf = None

class TTSEngine:
    _instance: Optional["TTSEngine"] = None
    _init_lock = threading.Lock()

    # Danh sách các giọng dựng sẵn theo vùng miền
    VOICES_METADATA = [
        {"id": "Hải Đăng", "name": "Hải Đăng", "gender": "Nam", "region": "Miền Bắc", "description": "Trầm ấm, truyền cảm, tự nhiên"},
        {"id": "Ngọc", "name": "Ngọc", "gender": "Nữ", "region": "Miền Bắc", "description": "Thanh thoát, dịu dàng, phát âm chuẩn"},
        {"id": "Bình", "name": "Bình", "gender": "Nam", "region": "Miền Trung", "description": "Dứt khoát, mộc mạc, đậm chất miền Trung"},
        {"id": "Đoan", "name": "Đoan", "gender": "Nữ", "region": "Miền Trung", "description": "Ngọt ngào, nhẹ nhàng, sâu lắng"},
        {"id": "Tuyên", "name": "Tuyên", "gender": "Nam", "region": "Miền Nam", "description": "Hào sảng, hiện đại, phóng khoáng"},
        {"id": "Mai", "name": "Mai", "gender": "Nữ", "region": "Miền Nam", "description": "Trong trẻo, tươi sáng, hoạt bát"}
    ]

    SUPPORTED_TAGS = [
        {"tag": "[cười]", "description": "Tiếng cười tự nhiên trong câu"},
        {"tag": "[thở dài]", "description": "Tiếng thở dài thể hiện tâm trạng"},
        {"tag": "[hắng giọng]", "description": "Hắng giọng, lấy giọng nói"},
        {"tag": "[ngạc nhiên]", "description": "Biểu cảm ngạc nhiên, bất ngờ"},
        {"tag": "[ngập ngừng]", "description": "Khoảng lặng do dự, suy nghĩ"}
    ]

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super(TTSEngine, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.model_name = os.getenv("VIENEU_MODEL", "v3turbo")
        self.precision = os.getenv("VIENEU_PRECISION", "int8")
        self.device = os.getenv("VIENEU_DEVICE", "cpu")
        self.sample_rate = 48000
        self.infer_lock = threading.Lock()
        self.tts = None
        self.is_loaded = False
        self.error_message = None

        self._load_model()
        self._initialized = True

    def _load_model(self):
        if np is None or sf is None:
            self.error_message = "Thiếu thư viện xử lý âm thanh 'numpy' hoặc 'soundfile'. Hãy chạy: pip install -r backend/requirements.txt"
            logger.warning(self.error_message)
            self.is_loaded = False
            return

        logger.info(f"Đang khởi tạo VieNeu-TTS Engine (Model: {self.model_name}, Precision: {self.precision}, Device: {self.device})...")
        try:
            from vieneu import Vieneu
            # Khởi tạo mô hình VieNeu
            # Hỗ trợ truyền tham số linh hoạt theo phiên bản SDK vieneu
            try:
                self.tts = Vieneu(
                    model_name=self.model_name,
                    precision=self.precision,
                    device=self.device
                )
            except TypeError:
                # Fallback nếu Vieneu() dùng tên tham số khác hoặc mặc định
                logger.warning("Vieneu init không nhận các tham số tuỳ chỉnh, dùng khởi tạo mặc định Vieneu()...")
                self.tts = Vieneu()

            self.is_loaded = True
            logger.info("VieNeu-TTS Engine đã nạp thành công vào RAM và sẵn sàng phục vụ.")
        except ImportError as e:
            self.error_message = f"Chưa cài đặt thư viện 'vieneu'. Hãy chạy: pip install vieneu ({str(e)})"
            logger.warning(self.error_message)
            self.is_loaded = False
        except Exception as e:
            self.error_message = f"Lỗi khởi tạo mô hình VieNeu: {str(e)}"
            logger.error(self.error_message, exc_info=True)
            self.is_loaded = False

    def is_ready(self) -> bool:
        return self.is_loaded and self.tts is not None

    def get_info(self) -> Dict[str, Any]:
        return {
            "status": "ready" if self.is_ready() else "not_ready",
            "model_name": self.model_name,
            "precision": self.precision,
            "device": self.device,
            "sample_rate": self.sample_rate,
            "error": self.error_message
        }

    def infer(self, text: str, voice: Optional[str] = "Hải Đăng", ref_audio_path: Optional[str] = None, denoise: bool = True) -> io.BytesIO:
        """
        Thực hiện tổng hợp tiếng nói an toàn luồng (Thread-safe) qua self.infer_lock.
        Cung cấp 2 chế độ:
        1. Giọng dựng sẵn (voice)
        2. Nhân bản giọng nói (Voice Cloning qua ref_audio_path)
        """
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Văn bản tổng hợp không được để trống.")

        # Xếp hàng đơn luồng trên CPU để tránh tắc nghẽn hoặc tràn RAM
        with self.infer_lock:
            if not self.is_ready():
                # Fallback cho môi trường dev/kiểm thử cục bộ nếu chưa có model thật
                logger.warning("Mô hình chưa sẵn sàng, kích hoạt chế độ fallback sinh âm thanh kiểm thử...")
                return self._generate_fallback_audio(cleaned_text)

            try:
                # Thực hiện gọi suy luận từ SDK vieneu
                if ref_audio_path and os.path.exists(ref_audio_path):
                    logger.info(f"Bắt đầu Voice Cloning từ file mẫu: {ref_audio_path} (Denoise={denoise})")
                    audio_output = self.tts.infer(
                        text=cleaned_text,
                        ref_audio=ref_audio_path,
                        denoise=denoise
                    )
                else:
                    target_voice = voice if voice else "Hải Đăng"
                    logger.info(f"Bắt đầu tổng hợp giọng có sẵn: '{target_voice}'")
                    audio_output = self.tts.infer(
                        text=cleaned_text,
                        voice=target_voice,
                        denoise=denoise
                    )

                return self._convert_to_wav_io(audio_output)

            except Exception as e:
                logger.error(f"Lỗi trong quá trình suy luận TTS: {str(e)}", exc_info=True)
                raise RuntimeError(f"Lỗi suy luận TTS: {str(e)}")

    def _convert_to_wav_io(self, audio_output: Any) -> io.BytesIO:
        """
        Chuyển đổi kết quả audio_output từ vieneu thành io.BytesIO định dạng WAV 48kHz.
        """
        buffer = io.BytesIO()

        # Trường hợp 1: audio_output là numpy array
        if isinstance(audio_output, np.ndarray):
            sf.write(buffer, audio_output, self.sample_rate, format="WAV", subtype="PCM_16")
            buffer.seek(0)
            return buffer

        # Trường hợp 2: audio_output là tuple (audio_data, sr)
        if isinstance(audio_output, tuple) and len(audio_output) >= 2:
            data, sr = audio_output[0], audio_output[1]
            sf.write(buffer, data, sr, format="WAV", subtype="PCM_16")
            buffer.seek(0)
            return buffer

        # Trường hợp 3: dùng phương thức tts.save của SDK để ghi ra file tạm rồi đọc lại
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            if hasattr(self.tts, "save"):
                self.tts.save(audio_output, tmp_path)
            else:
                raise ValueError("Không thể nhận diện định dạng audio trả về từ VieNeu")

            with open(tmp_path, "rb") as f:
                buffer.write(f.read())
            buffer.seek(0)
            return buffer
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _generate_fallback_audio(self, text: str) -> io.BytesIO:
        """
        Tạo file WAV sóng âm kiểm thử chuẩn 48kHz để kiểm tra toàn bộ luồng mạng & giao diện
        khi chưa cài đặt mô hình hoặc trên môi trường kiểm thử.
        """
        duration = min(max(len(text) * 0.08, 1.5), 6.0)
        t = np.linspace(0, duration, int(self.sample_rate * duration), endpoint=False)
        # Sóng hài êm dịu mô phỏng âm thanh
        tone = 0.25 * np.sin(2 * np.pi * 330 * t) + 0.15 * np.sin(2 * np.pi * 440 * t)
        # Envelope mượt mà đầu và cuối
        envelope = np.ones_like(tone)
        fade_samples = int(self.sample_rate * 0.1)
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        audio = (tone * envelope).astype(np.float32)

        buffer = io.BytesIO()
        sf.write(buffer, audio, self.sample_rate, format="WAV", subtype="PCM_16")
        buffer.seek(0)
        return buffer

# Khởi tạo instance toàn cục (Singleton)
def get_tts_engine() -> TTSEngine:
    return TTSEngine()
