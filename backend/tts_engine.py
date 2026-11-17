import io
import os
import json
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

    # Danh mục 25 giọng đọc chuẩn mực của VieNeu-TTS v3 Turbo phân nhóm 3 miền
    FALLBACK_VOICES_METADATA = [
        # --- MIỀN TRUNG ---
        {"id": "Quang Sơn", "name": "Quang Sơn", "gender": "Nam", "region": "Miền Trung", "description": "Nam · Miền Trung · Tự nhiên, mộc mạc", "style": "Tự nhiên"},
        {"id": "Ngọc Trân", "name": "Ngọc Trân", "gender": "Nữ", "region": "Miền Trung", "description": "Nữ · Miền Trung · Ngọt ngào, sâu lắng", "style": "Tự nhiên"},

        # --- MIỀN NAM ---
        {"id": "Thùy Dung", "name": "Thùy Dung", "gender": "Nữ", "region": "Miền Nam", "description": "Nữ · Miền Nam · Tin tức, chuẩn mực", "style": "Tin tức"},
        {"id": "Thái Sơn", "name": "Thái Sơn", "gender": "Nam", "region": "Miền Nam", "description": "Nam · Miền Nam · Kể chuyện, trầm ấm", "style": "Kể chuyện"},
        {"id": "Thục Đoan", "name": "Thục Đoan", "gender": "Nữ", "region": "Miền Nam", "description": "Nữ · Miền Nam · Kể chuyện, nhẹ nhàng", "style": "Kể chuyện"},
        {"id": "Minh Triết", "name": "Minh Triết", "gender": "Nam", "region": "Miền Nam", "description": "Nam · Miền Nam · Tin tức, hiện đại", "style": "Tin tức"},
        {"id": "Mỹ Duyên", "name": "Mỹ Duyên", "gender": "Nữ", "region": "Miền Nam", "description": "Nữ · Miền Nam · Đọc truyện, cuốn hút", "style": "Đọc truyện"},
        {"id": "Đức Trí", "name": "Đức Trí", "gender": "Nam", "region": "Miền Nam", "description": "Nam · Miền Nam · Đọc truyện, truyền cảm", "style": "Đọc truyện"},
        {"id": "Kim Thanh", "name": "Kim Thanh", "gender": "Nữ", "region": "Miền Nam", "description": "Nữ · Miền Nam · Đọc truyện, mượt mà", "style": "Đọc truyện"},
        {"id": "Adam", "name": "Adam", "gender": "Nam", "region": "Miền Nam", "description": "Nam · Miền Nam · Giọng đọc tự nhiên, phóng khoáng", "style": "Tự nhiên"},

        # --- MIỀN BẮC ---
        {"id": "Hải Đăng", "name": "Hải Đăng", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Trầm ấm, truyền cảm (Mặc định)", "style": "Tự nhiên"},
        {"id": "Trúc Ly", "name": "Trúc Ly", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Thanh thoát, tự nhiên", "style": "Tự nhiên"},
        {"id": "Thiện Minh", "name": "Thiện Minh", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Kể chuyện, sâu sắc", "style": "Kể chuyện"},
        {"id": "Mai Anh", "name": "Mai Anh", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Tin tức, rõ ràng", "style": "Tin tức"},
        {"id": "Ngọc Huyền", "name": "Ngọc Huyền", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Tự nhiên, nhẹ nhàng", "style": "Tự nhiên"},
        {"id": "Minh Đức", "name": "Minh Đức", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Tin tức, chuẩn đài", "style": "Tin tức"},
        {"id": "Phạm Tuyên", "name": "Phạm Tuyên", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Tự nhiên, đĩnh đạc", "style": "Tự nhiên"},
        {"id": "Thanh Bình", "name": "Thanh Bình", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Kể chuyện, đầm ấm", "style": "Kể chuyện"},
        {"id": "Xuân Vĩnh", "name": "Xuân Vĩnh", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Tự nhiên, trẻ trung", "style": "Tự nhiên"},
        {"id": "Ngọc Linh", "name": "Ngọc Linh", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Kể chuyện, ấm áp", "style": "Kể chuyện"},
        {"id": "Đoan Trang", "name": "Đoan Trang", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Tự nhiên, duyên dáng", "style": "Tự nhiên"},
        {"id": "Quỳnh Anh", "name": "Quỳnh Anh", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Đọc truyện, dịu dàng", "style": "Đọc truyện"},
        {"id": "Quốc Tuấn", "name": "Quốc Tuấn", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Tự nhiên, khỏe khoắn", "style": "Tự nhiên"},
        {"id": "Thiền Tâm Đức", "name": "Thiền Tâm Đức", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Kể chuyện Phật giáo, tĩnh tâm", "style": "Kể chuyện"},
        {"id": "Adam bựa", "name": "Adam bựa", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Hài hước, tếu táo", "style": "Tự nhiên"}
    ]

    # Alias mapping thông minh để bắt các tên rút gọn người dùng gõ
    VOICE_ALIASES = {
        "hải đăng": "Hải Đăng",
        "trúc ly": "Trúc Ly",
        "thiện minh": "Thiện Minh",
        "mai anh": "Mai Anh",
        "mai": "Mai Anh",
        "ngọc huyền": "Ngọc Huyền",
        "ngọc": "Ngọc Huyền",
        "ngọc trân": "Ngọc Trân",
        "quang sơn": "Quang Sơn",
        "sơn": "Quang Sơn",
        "thùy dung": "Thùy Dung",
        "dung": "Thùy Dung",
        "thái sơn": "Thái Sơn",
        "thục đoan": "Thục Đoan",
        "đoan": "Thục Đoan",
        "đoan trang": "Đoan Trang",
        "minh đức": "Minh Đức",
        "phạm tuyên": "Phạm Tuyên",
        "tuyên": "Phạm Tuyên",
        "thanh bình": "Thanh Bình",
        "bình": "Thanh Bình",
        "xuân vĩnh": "Xuân Vĩnh",
        "vĩnh": "Xuân Vĩnh",
        "ngọc linh": "Ngọc Linh",
        "linh": "Ngọc Linh",
        "quỳnh anh": "Quỳnh Anh",
        "minh triết": "Minh Triết",
        "mỹ duyên": "Mỹ Duyên",
        "đức trí": "Đức Trí",
        "kim thanh": "Kim Thanh",
        "quốc tuấn": "Quốc Tuấn",
        "tuấn": "Quốc Tuấn",
        "adam": "Adam",
        "adam bựa": "Adam bựa"
    }

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
        self.voices_list = self._init_voices()

        self._load_model()
        self._initialized = True

    def _init_voices(self) -> List[Dict[str, Any]]:
        """
        Nạp danh sách giọng đọc từ thư viện vieneu nếu có file voices_v3_turbo.json,
        nếu không thì dùng danh sách FALLBACK_VOICES_METADATA.
        """
        try:
            import vieneu
            pkg_dir = os.path.dirname(vieneu.__file__)
            json_path = os.path.join(pkg_dir, "assets", "voices_v3_turbo.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    presets = data.get("presets", {})
                    if presets:
                        parsed = []
                        for name, info in presets.items():
                            region = info.get("region", "Bắc")
                            if region == "Bắc":
                                region_name = "Miền Bắc"
                            elif region == "Trung":
                                region_name = "Miền Trung"
                            else:
                                region_name = "Miền Nam"
                            gender = "Nam" if info.get("gender") == "male" else "Nữ"
                            parsed.append({
                                "id": name,
                                "name": name,
                                "gender": gender,
                                "region": region_name,
                                "description": info.get("description", f"{gender} · {region_name}"),
                                "style": info.get("style", "Tự nhiên")
                            })
                        region_order = {"Miền Trung": 1, "Miền Nam": 2, "Miền Bắc": 3}
                        parsed.sort(key=lambda x: (region_order.get(x["region"], 9), x["gender"], x["name"]))
                        logger.info(f"Đã nạp thành công {len(parsed)} giọng đọc từ {json_path}")
                        return parsed
        except Exception as e:
            logger.warning(f"Không thể đọc voices_v3_turbo.json từ vieneu: {e}")

        return self.FALLBACK_VOICES_METADATA

    def _load_model(self):
        if np is None or sf is None:
            self.error_message = "Thiếu thư viện xử lý âm thanh 'numpy' hoặc 'soundfile'. Hãy chạy: pip install -r backend/requirements.txt"
            logger.warning(self.error_message)
            self.is_loaded = False
            return

        logger.info(f"Đang khởi tạo VieNeu-TTS Engine (Model: {self.model_name}, Precision: {self.precision}, Device: {self.device})...")
        try:
            from vieneu import Vieneu
            try:
                self.tts = Vieneu(
                    model_name=self.model_name,
                    precision=self.precision,
                    device=self.device
                )
            except TypeError:
                logger.warning("Vieneu init dùng tham số mặc định Vieneu()...")
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
            "total_voices": len(self.voices_list),
            "error": self.error_message
        }

    def resolve_voice_name(self, raw_voice: Optional[str]) -> str:
        """
        Chuẩn hóa tên giọng dựa trên alias mapping để đảm bảo luôn khớp
        với tên preset chính thức trong VieNeu.
        """
        if not raw_voice:
            return "Hải Đăng"

        cleaned = raw_voice.strip()
        lower = cleaned.lower()

        if lower in self.VOICE_ALIASES:
            return self.VOICE_ALIASES[lower]

        for v in self.voices_list:
            if v["id"].lower() == lower or v["name"].lower() == lower:
                return v["id"]

        logger.warning(f"Không tìm thấy giọng '{raw_voice}', sử dụng giọng mặc định 'Hải Đăng'")
        return "Hải Đăng"

    def infer(self, text: str, voice: Optional[str] = "Hải Đăng", ref_audio_path: Optional[str] = None, denoise: bool = True) -> io.BytesIO:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Văn bản tổng hợp không được để trống.")

        with self.infer_lock:
            if not self.is_ready():
                logger.warning("Mô hình chưa sẵn sàng, kích hoạt fallback sóng âm...")
                return self._generate_fallback_audio(cleaned_text)

            try:
                if ref_audio_path and os.path.exists(ref_audio_path):
                    logger.info(f"Bắt đầu Voice Cloning từ file mẫu: {ref_audio_path} (Denoise={denoise})")
                    audio_output = self.tts.infer(
                        text=cleaned_text,
                        ref_audio=ref_audio_path,
                        denoise=denoise
                    )
                else:
                    target_voice = self.resolve_voice_name(voice)
                    logger.info(f"Bắt đầu tổng hợp giọng chuẩn: '{target_voice}' (input: '{voice}')")
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
        buffer = io.BytesIO()

        if np is not None and isinstance(audio_output, np.ndarray):
            sf.write(buffer, audio_output, self.sample_rate, format="WAV", subtype="PCM_16")
            buffer.seek(0)
            return buffer

        if np is not None and isinstance(audio_output, tuple) and len(audio_output) >= 2:
            data, sr = audio_output[0], audio_output[1]
            sf.write(buffer, data, sr, format="WAV", subtype="PCM_16")
            buffer.seek(0)
            return buffer

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
        if np is None or sf is None:
            raise RuntimeError(self.error_message or "Thiếu numpy/soundfile")

        duration = min(max(len(text) * 0.08, 1.5), 6.0)
        t = np.linspace(0, duration, int(self.sample_rate * duration), endpoint=False)
        tone = 0.25 * np.sin(2 * np.pi * 330 * t) + 0.15 * np.sin(2 * np.pi * 440 * t)
        envelope = np.ones_like(tone)
        fade_samples = int(self.sample_rate * 0.1)
        envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
        envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
        audio = (tone * envelope).astype(np.float32)

        buffer = io.BytesIO()
        sf.write(buffer, audio, self.sample_rate, format="WAV", subtype="PCM_16")
        buffer.seek(0)
        return buffer

def get_tts_engine() -> TTSEngine:
    return TTSEngine()
