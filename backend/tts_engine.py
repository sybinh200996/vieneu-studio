import io
import os
import json
import logging
import threading
import tempfile
from typing import Optional, List, Dict, Any

from backend.edge_engine import get_edge_engine, EDGE_VOICES_METADATA
from backend.voicepack_engine import get_voicepack_engine

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

    # Danh mục 25 giọng đọc chuẩn mực nội bộ của VieNeu-TTS v3 Turbo
    FALLBACK_VOICES_METADATA = [
        # --- MIỀN TRUNG ---
        {"id": "Quang Sơn", "name": "Quang Sơn", "gender": "Nam", "region": "Miền Trung", "description": "Nam · Miền Trung · Tự nhiên, mộc mạc", "style": "Tự nhiên", "engine": "vieneu"},
        {"id": "Ngọc Trân", "name": "Ngọc Trân", "gender": "Nữ", "region": "Miền Trung", "description": "Nữ · Miền Trung · Ngọt ngào, sâu lắng", "style": "Tự nhiên", "engine": "vieneu"},

        # --- MIỀN NAM ---
        {"id": "Thùy Dung", "name": "Thùy Dung", "gender": "Nữ", "region": "Miền Nam", "description": "Nữ · Miền Nam · Tin tức, chuẩn mực", "style": "Tin tức", "engine": "vieneu"},
        {"id": "Thái Sơn", "name": "Thái Sơn", "gender": "Nam", "region": "Miền Nam", "description": "Nam · Miền Nam · Kể chuyện, trầm ấm", "style": "Kể chuyện", "engine": "vieneu"},
        {"id": "Thục Đoan", "name": "Thục Đoan", "gender": "Nữ", "region": "Miền Nam", "description": "Nữ · Miền Nam · Kể chuyện, nhẹ nhàng", "style": "Kể chuyện", "engine": "vieneu"},
        {"id": "Minh Triết", "name": "Minh Triết", "gender": "Nam", "region": "Miền Nam", "description": "Nam · Miền Nam · Tin tức, hiện đại", "style": "Tin tức", "engine": "vieneu"},
        {"id": "Mỹ Duyên", "name": "Mỹ Duyên", "gender": "Nữ", "region": "Miền Nam", "description": "Nữ · Miền Nam · Đọc truyện, cuốn hút", "style": "Đọc truyện", "engine": "vieneu"},
        {"id": "Đức Trí", "name": "Đức Trí", "gender": "Nam", "region": "Miền Nam", "description": "Nam · Miền Nam · Đọc truyện, truyền cảm", "style": "Đọc truyện", "engine": "vieneu"},
        {"id": "Kim Thanh", "name": "Kim Thanh", "gender": "Nữ", "region": "Miền Nam", "description": "Nữ · Miền Nam · Đọc truyện, mượt mà", "style": "Đọc truyện", "engine": "vieneu"},
        {"id": "Adam", "name": "Adam", "gender": "Nam", "region": "Miền Nam", "description": "Nam · Miền Nam · Giọng đọc tự nhiên, phóng khoáng", "style": "Tự nhiên", "engine": "vieneu"},

        # --- MIỀN BẮC ---
        {"id": "Hải Đăng", "name": "Hải Đăng", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Trầm ấm, truyền cảm (Mặc định)", "style": "Tự nhiên", "engine": "vieneu"},
        {"id": "Trúc Ly", "name": "Trúc Ly", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Thanh thoát, tự nhiên", "style": "Tự nhiên", "engine": "vieneu"},
        {"id": "Thiện Minh", "name": "Thiện Minh", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Kể chuyện, sâu sắc", "style": "Kể chuyện", "engine": "vieneu"},
        {"id": "Mai Anh", "name": "Mai Anh", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Tin tức, rõ ràng", "style": "Tin tức", "engine": "vieneu"},
        {"id": "Ngọc Huyền", "name": "Ngọc Huyền", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Tự nhiên, nhẹ nhàng", "style": "Tự nhiên", "engine": "vieneu"},
        {"id": "Minh Đức", "name": "Minh Đức", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Tin tức, chuẩn đài", "style": "Tin tức", "engine": "vieneu"},
        {"id": "Phạm Tuyên", "name": "Phạm Tuyên", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Tự nhiên, đĩnh đạc", "style": "Tự nhiên", "engine": "vieneu"},
        {"id": "Thanh Bình", "name": "Thanh Bình", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Kể chuyện, đầm ấm", "style": "Kể chuyện", "engine": "vieneu"},
        {"id": "Xuân Vĩnh", "name": "Xuân Vĩnh", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Tự nhiên, trẻ trung", "style": "Tự nhiên", "engine": "vieneu"},
        {"id": "Ngọc Linh", "name": "Ngọc Linh", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Kể chuyện, ấm áp", "style": "Kể chuyện", "engine": "vieneu"},
        {"id": "Đoan Trang", "name": "Đoan Trang", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Tự nhiên, duyên dáng", "style": "Tự nhiên", "engine": "vieneu"},
        {"id": "Quỳnh Anh", "name": "Quỳnh Anh", "gender": "Nữ", "region": "Miền Bắc", "description": "Nữ · Miền Bắc · Đọc truyện, dịu dàng", "style": "Đọc truyện", "engine": "vieneu"},
        {"id": "Quốc Tuấn", "name": "Quốc Tuấn", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Tự nhiên, khỏe khoắn", "style": "Tự nhiên", "engine": "vieneu"},
        {"id": "Thiền Tâm Đức", "name": "Thiền Tâm Đức", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Kể chuyện Phật giáo, tĩnh tâm", "style": "Kể chuyện", "engine": "vieneu"},
        {"id": "Adam bựa", "name": "Adam bựa", "gender": "Nam", "region": "Miền Bắc", "description": "Nam · Miền Bắc · Hài hước, tếu táo", "style": "Tự nhiên", "engine": "vieneu"}
    ]

    # Alias mapping thông minh để bắt các tên rút gọn người dùng gõ
    VOICE_ALIASES = {
        # Edge Neural
        "hoài my": "vi-VN-HoaiMyNeural",
        "hoaimy": "vi-VN-HoaiMyNeural",
        "vi-vn-hoaimyneural": "vi-VN-HoaiMyNeural",
        "nam minh": "vi-VN-NamMinhNeural",
        "namminh": "vi-VN-NamMinhNeural",
        "vi-vn-namminhneural": "vi-VN-NamMinhNeural",

        # Custom Voicepacks
        "mc thời sự nam": "VP_MC_Nam",
        "mc vtv nam": "VP_MC_Nam",
        "mc nam": "VP_MC_Nam",
        "vp_mc_nam": "VP_MC_Nam",

        "mc thời sự nữ": "VP_MC_Nu",
        "mc vtv nữ": "VP_MC_Nu",
        "mc nữ": "VP_MC_Nu",
        "vp_mc_nu": "VP_MC_Nu",

        "kể chuyện đêm": "VP_KeChuyenDem",
        "kể chuyện đêm khuya": "VP_KeChuyenDem",
        "chuyện đêm": "VP_KeChuyenDem",
        "vp_kechuyendem": "VP_KeChuyenDem",

        "nữ huế": "VP_NuHue",
        "huế": "VP_NuHue",
        "vp_nuhue": "VP_NuHue",

        "nữ miền tây": "VP_NuMienTay",
        "miền tây": "VP_NuMienTay",
        "vp_numientay": "VP_NuMienTay",

        "review phim": "VP_ReviewPhim",
        "tóm tắt phim": "VP_ReviewPhim",
        "vp_reviewphim": "VP_ReviewPhim",

        # VieNeu Presets
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
        {"tag": "[cười]", "description": "Tiếng cười tự nhiên trong câu (VieNeu Engine)"},
        {"tag": "[thở dài]", "description": "Tiếng thở dài thể hiện tâm trạng (VieNeu Engine)"},
        {"tag": "[hắng giọng]", "description": "Hắng giọng, lấy giọng nói (VieNeu Engine)"},
        {"tag": "[ngạc nhiên]", "description": "Biểu cảm ngạc nhiên, bất ngờ (VieNeu Engine)"},
        {"tag": "[ngập ngừng]", "description": "Khoảng lặng do dự, suy nghĩ (VieNeu Engine)"}
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

        # Nạp danh sách đa nguồn (VieNeu + Custom Voicepacks + Edge Neural)
        self.voices_list = self._init_all_voices()

        self._load_model()
        self._initialized = True

    def _init_all_voices(self) -> List[Dict[str, Any]]:
        """
        Nạp hợp nhất danh sách giọng từ:
        1. Edge Neural Voices (Hoài My, Nam Minh)
        2. Custom Voicepacks (MC Thời Sự, Kể Chuyện Đêm, Nữ Huế...)
        3. VieNeu-TTS Presets (25 giọng)
        """
        all_voices = []

        # 1. Thêm Edge Neural Voices
        all_voices.extend(EDGE_VOICES_METADATA)

        # 2. Thêm Voicepacks
        try:
            vp_engine = get_voicepack_engine()
            vps = vp_engine.get_voicepacks()
            all_voices.extend(vps)
        except Exception as e:
            logger.warning(f"Không thể nạp voicepacks: {e}")

        # 3. Thêm VieNeu Presets
        vieneu_voices = self._load_vieneu_presets()
        all_voices.extend(vieneu_voices)

        logger.info(f"Đã nạp tổng cộng {len(all_voices)} giọng đọc vào Multi-Engine Router.")
        return all_voices

    def _load_vieneu_presets(self) -> List[Dict[str, Any]]:
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
                                "style": info.get("style", "Tự nhiên"),
                                "engine": "vieneu"
                            })
                        region_order = {"Miền Trung": 1, "Miền Nam": 2, "Miền Bắc": 3}
                        parsed.sort(key=lambda x: (region_order.get(x["region"], 9), x["gender"], x["name"]))
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
            "supported_engines": ["vieneu", "voicepack", "edge"],
            "error": self.error_message
        }

    def resolve_voice_info(self, raw_voice: Optional[str]) -> Dict[str, Any]:
        """
        Tìm kiếm thông tin giọng và engine xử lý từ tên voice hoặc alias.
        """
        if not raw_voice:
            return {"id": "Hải Đăng", "engine": "vieneu", "name": "Hải Đăng"}

        cleaned = raw_voice.strip()
        lower = cleaned.lower()

        # Check alias map
        target_id = self.VOICE_ALIASES.get(lower, cleaned)

        # Tìm trong voices_list
        for v in self.voices_list:
            if v["id"].lower() == target_id.lower() or v["name"].lower() == target_id.lower() or v["id"].lower() == lower or v["name"].lower() == lower:
                return v

        # Fallback về Hải Đăng nếu không thấy
        logger.warning(f"Không tìm thấy giọng '{raw_voice}', sử dụng giọng mặc định 'Hải Đăng'")
        return {"id": "Hải Đăng", "engine": "vieneu", "name": "Hải Đăng"}

    def infer(self, text: str, voice: Optional[str] = "Hải Đăng", ref_audio_path: Optional[str] = None, denoise: bool = True) -> io.BytesIO:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Văn bản tổng hợp không được để trống.")

        # TRƯỜNG HỢP 1: Người dùng upload / ghi âm file mẫu (Custom Voice Cloning trực tiếp)
        if ref_audio_path and os.path.exists(ref_audio_path):
            with self.infer_lock:
                if not self.is_ready():
                    return self._generate_fallback_audio(cleaned_text)
                logger.info(f"Bắt đầu Voice Cloning từ file mẫu người dùng: {ref_audio_path} (Denoise={denoise})")
                audio_output = self.tts.infer(
                    text=cleaned_text,
                    ref_audio=ref_audio_path,
                    denoise=denoise
                )
                return self._convert_to_wav_io(audio_output)

        # TRƯỜNG HỢP 2: Sử dụng giọng có sẵn qua Multi-Engine Router
        voice_info = self.resolve_voice_info(voice)
        engine_type = voice_info.get("engine", "vieneu")
        voice_id = voice_info.get("id", "Hải Đăng")

        # --- A. XỬ LÝ QUA EDGE-TTS (Tốc độ cao, 0MB RAM) ---
        if engine_type == "edge":
            logger.info(f"Định tuyến tới Edge-TTS Engine: '{voice_id}' (Voice: {voice_info.get('name')})")
            edge_engine = get_edge_engine()
            return edge_engine.synthesize(text=cleaned_text, voice=voice_id)

        # --- B. XỬ LÝ QUA CUSTOM VOICEPACKS (VieNeu Prompt Audio) ---
        if engine_type == "voicepack":
            vp_engine = get_voicepack_engine()
            sample_path = vp_engine.get_sample_path(voice_id)
            if sample_path and os.path.exists(sample_path):
                logger.info(f"Định tuyến tới Voicepack: '{voice_info.get('name')}' qua mẫu: {sample_path}")
                with self.infer_lock:
                    if not self.is_ready():
                        return self._generate_fallback_audio(cleaned_text)
                    audio_output = self.tts.infer(
                        text=cleaned_text,
                        ref_audio=sample_path,
                        denoise=True
                    )
                    return self._convert_to_wav_io(audio_output)
            else:
                logger.warning(f"Không tìm thấy file mẫu cho voicepack '{voice_id}', fallback về Hải Đăng")
                voice_id = "Hải Đăng"

        # --- C. XỬ LÝ QUA VIENEU PRESETS (25 giọng chuẩn) ---
        with self.infer_lock:
            if not self.is_ready():
                logger.warning("Mô hình VieNeu chưa sẵn sàng, kích hoạt fallback sóng âm...")
                return self._generate_fallback_audio(cleaned_text)

            try:
                logger.info(f"Định tuyến tới VieNeu Engine: '{voice_id}' (Input: '{voice}')")
                audio_output = self.tts.infer(
                    text=cleaned_text,
                    voice=voice_id,
                    denoise=denoise
                )
                return self._convert_to_wav_io(audio_output)
            except Exception as e:
                logger.error(f"Lỗi suy luận VieNeu TTS: {str(e)}", exc_info=True)
                raise RuntimeError(f"Lỗi suy luận VieNeu TTS: {str(e)}")

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
