import io
import os
import re
import time
import json
import hashlib
import logging
import threading
import tempfile
from typing import Optional, List, Dict, Any

from backend.edge_engine import get_edge_engine, EDGE_VOICES_METADATA
from backend.voicepack_engine import get_voicepack_engine

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TTSEngine")

ALLOWED_REF_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}
CACHE_TTL_SECONDS = 24 * 3600  # 24 giờ
CACHE_CLEANUP_INTERVAL = 1800  # Dọn dẹp tối đa mỗi 30 phút

class CPUQueueFullError(Exception):
    """Bắn ra khi số lượng request TTS trên CPU vượt quá giới hạn BoundedSemaphore (tối đa 4 request chờ)"""
    pass

class ModelNotReadyError(Exception):
    """Bắn ra khi engine CPU (VieNeu / Voicepack) chưa sẵn sàng phục vụ"""
    pass

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
        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            self.model_name = os.getenv("VIENEU_MODEL", "v3turbo")
            self.precision = os.getenv("VIENEU_PRECISION", "int8")
            self.device = os.getenv("VIENEU_DEVICE", "cpu")
            self.sample_rate = 48000
            self.infer_lock = threading.Lock()
            # Chốt chặn hàng đợi CPU: Tối đa 4 request chờ đồng thời trên 2 vCPU
            self.cpu_semaphore = threading.BoundedSemaphore(4)
            self.tts = None
            self.is_loaded = False
            self.error_message = None

            # Thư mục Disk Cache WAV (SSD) + khóa thời điểm dọn dẹp
            self._cache_dir = os.path.join(tempfile.gettempdir(), "vieneu_tts_cache")
            os.makedirs(self._cache_dir, exist_ok=True)
            self._cache_cleanup_lock = threading.Lock()
            self._last_cache_cleanup = 0.0

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

    @staticmethod
    def chunk_text(text: str, max_chars: int = 320) -> List[str]:
        """
        Chia nhỏ văn bản dài thành các đoạn ngắn (~200 - 320 ký tự) theo ranh giới câu tự nhiên.
        Đảm bảo không cắt ngang từ ngữ, giúp giữ RAM ổn định và giải phóng CPU tuần tự.
        """
        clean = text.strip()
        if len(clean) <= max_chars:
            return [clean]

        raw_sentences = re.split(r'([.!?;\n]+)', clean)
        sentences = []
        for i in range(0, len(raw_sentences) - 1, 2):
            s = (raw_sentences[i] + raw_sentences[i+1]).strip()
            if s:
                sentences.append(s)
        if len(raw_sentences) % 2 == 1 and raw_sentences[-1].strip():
            sentences.append(raw_sentences[-1].strip())

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(sentence) > max_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                sub_parts = re.split(r'([,，]+)', sentence)
                sub_sentences = []
                for j in range(0, len(sub_parts) - 1, 2):
                    sp = (sub_parts[j] + sub_parts[j+1]).strip()
                    if sp:
                        sub_sentences.append(sp)
                if len(sub_parts) % 2 == 1 and sub_parts[-1].strip():
                    sub_sentences.append(sub_parts[-1].strip())

                for sub in sub_sentences:
                    if len(sub) > max_chars:
                        words = sub.split()
                        w_chunk = ""
                        for w in words:
                            if len(w) > max_chars:
                                if w_chunk:
                                    chunks.append(w_chunk)
                                    w_chunk = ""
                                for k in range(0, len(w), max_chars):
                                    part = w[k:k + max_chars]
                                    if len(part) == max_chars:
                                        chunks.append(part)
                                    else:
                                        w_chunk = part
                            elif len(w_chunk) + len(w) + 1 <= max_chars:
                                w_chunk = f"{w_chunk} {w}".strip()
                            else:
                                if w_chunk:
                                    chunks.append(w_chunk)
                                w_chunk = w
                        if w_chunk:
                            chunks.append(w_chunk)
                    else:
                        if len(current_chunk) + len(sub) + 1 <= max_chars:
                            current_chunk = f"{current_chunk} {sub}".strip()
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = sub
            else:
                if len(current_chunk) + len(sentence) + 1 <= max_chars:
                    current_chunk = f"{current_chunk} {sentence}".strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return [c for c in chunks if c.strip()]

    def _validate_ref_audio_path(self, ref_audio_path: Optional[str]) -> Optional[str]:
        """Kiểm tra đường dẫn file mẫu an toàn: chặn path traversal, chỉ nhận file hợp lệ trong thư mục cho phép."""
        if not ref_audio_path:
            return None

        real_path = os.path.realpath(ref_audio_path)
        if not os.path.isfile(real_path):
            raise ValueError("File âm thanh mẫu không tồn tại.")

        ext = os.path.splitext(real_path)[1].lower()
        if ext not in ALLOWED_REF_EXTENSIONS:
            raise ValueError(f"Định dạng file mẫu không hợp lệ: '{ext}'")

        allowed_roots = [
            os.path.realpath(tempfile.gettempdir()),
            os.path.realpath(os.path.join(os.path.dirname(__file__), "voicepacks")),
        ]
        is_allowed = False
        for root in allowed_roots:
            try:
                if os.path.commonpath([root, real_path]) == root:
                    is_allowed = True
                    break
            except ValueError:
                continue

        if not is_allowed:
            logger.warning(f"Chặn truy cập file mẫu ngoài vùng cho phép: {ref_audio_path}")
            raise ValueError("Đường dẫn file âm thanh mẫu không được phép.")

        return real_path

    def _get_cache_path(self, engine_type: str, voice_id: str, text: str, denoise: bool) -> str:
        raw_key = f"{engine_type}|{voice_id}|{text}|{bool(denoise)}".encode("utf-8")
        digest = hashlib.sha256(raw_key).hexdigest()
        return os.path.join(self._cache_dir, f"{digest}.wav")

    def _read_cache(self, cache_path: str) -> Optional[io.BytesIO]:
        try:
            if not os.path.isfile(cache_path):
                return None
            stat = os.stat(cache_path)
            if time.time() - stat.st_mtime > CACHE_TTL_SECONDS:
                try:
                    os.remove(cache_path)
                except OSError:
                    pass
                return None
            if stat.st_size <= 44:
                return None
            with open(cache_path, "rb") as f:
                data = f.read()
            return io.BytesIO(data)
        except Exception as e:
            logger.warning(f"Lỗi đọc disk cache ({cache_path}): {e}")
            return None

    def _write_cache(self, cache_path: str, wav_buffer: io.BytesIO) -> None:
        try:
            data = wav_buffer.getvalue()
            if len(data) <= 44:
                return
            tmp_cache = f"{cache_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp_cache, "wb") as f:
                f.write(data)
            os.replace(tmp_cache, cache_path)
            wav_buffer.seek(0)
            self._cleanup_old_cache()
        except Exception as e:
            logger.warning(f"Không thể ghi disk cache ({cache_path}): {e}")

    def _cleanup_old_cache(self) -> None:
        now = time.time()
        if now - self._last_cache_cleanup < CACHE_CLEANUP_INTERVAL:
            return
        if not self._cache_cleanup_lock.acquire(blocking=False):
            return
        try:
            self._last_cache_cleanup = now
            removed = 0
            for entry in os.scandir(self._cache_dir):
                if entry.is_file():
                    try:
                        if now - entry.stat().st_mtime > CACHE_TTL_SECONDS:
                            os.remove(entry.path)
                            removed += 1
                    except OSError:
                        pass
            if removed:
                logger.info(f"Đã dọn {removed} file TTS cache cũ quá 24h.")
        except Exception as e:
            logger.warning(f"Lỗi dọn dẹp cache: {e}")
        finally:
            self._cache_cleanup_lock.release()

    def _infer_cpu_chunks(self, chunks: List[str], voice: Optional[str] = None, ref_audio: Optional[str] = None, denoise: bool = True) -> io.BytesIO:
        """
        Thực hiện suy luận tuần tự từng chunk trên CPU, nhả CPU và ghép các mảng numpy lại.
        Giúp đỉnh RAM phẳng lỳ và CPU không bị khóa cứng khi lồng tiếng văn bản dài.
        """
        if not self.is_ready():
            raise ModelNotReadyError(self.error_message or "Mô hình VieNeu-TTS chưa sẵn sàng trên CPU.")

        audio_parts = []
        pause_samples = int(self.sample_rate * 0.15)
        silence = np.zeros(pause_samples, dtype=np.float32) if np is not None else None

        for idx, chunk in enumerate(chunks):
            if len(chunks) > 1:
                logger.info(f"Đang tổng hợp chunk {idx+1}/{len(chunks)} ({len(chunk)} ký tự)...")
            
            if ref_audio:
                out = self.tts.infer(text=chunk, ref_audio=ref_audio, denoise=denoise)
            else:
                out = self.tts.infer(text=chunk, voice=voice, denoise=denoise)

            if np is not None and isinstance(out, np.ndarray):
                audio_parts.append(out)
            elif np is not None and isinstance(out, tuple) and len(out) >= 1:
                audio_parts.append(out[0])
            else:
                wav_io = self._convert_to_wav_io(out)
                if sf is not None:
                    data, _ = sf.read(wav_io)
                    audio_parts.append(data)

            if idx < len(chunks) - 1 and silence is not None:
                audio_parts.append(silence)
                time.sleep(0.01)

        if audio_parts and np is not None:
            combined = np.concatenate(audio_parts)
            return self._convert_to_wav_io(combined)
        elif audio_parts:
            return self._convert_to_wav_io(audio_parts[0])
        else:
            raise RuntimeError("Không tạo được dữ liệu âm thanh từ engine CPU.")

    def infer(self, text: str, voice: Optional[str] = "Hải Đăng", ref_audio_path: Optional[str] = None, denoise: bool = True) -> io.BytesIO:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Văn bản tổng hợp không được để trống.")

        valid_ref_path = self._validate_ref_audio_path(ref_audio_path)

        # Phân loại engine để điều hướng tối ưu tài nguyên
        voice_info = self.resolve_voice_info(voice)
        engine_type = voice_info.get("engine", "vieneu")
        voice_id = voice_info.get("id", "Hải Đăng")

        # Kiểm tra Disk Cache trước (chỉ cache khi không dùng file mẫu upload riêng)
        cache_path = None
        if not valid_ref_path:
            cache_path = self._get_cache_path(engine_type, voice_id, cleaned_text, denoise)
            cached_io = self._read_cache(cache_path)
            if cached_io is not None:
                logger.info(f"Disk Cache HIT [{engine_type}:{voice_id}] ({len(cleaned_text)} ký tự)")
                return cached_io

        # --- A. XỬ LÝ QUA EDGE-TTS (Tốc độ cao, Cloud 0MB RAM, không dùng CPU semaphore) ---
        if engine_type == "edge" and not valid_ref_path:
            logger.info(f"Định tuyến tới Edge-TTS Engine: '{voice_id}' (Voice: {voice_info.get('name')})")
            edge_engine = get_edge_engine()
            wav_io = edge_engine.synthesize(text=cleaned_text, voice=voice_id)
            if cache_path:
                self._write_cache(cache_path, wav_io)
            return wav_io

        # --- B. CÁC TÁC VỤ CPU (VieNeu / Voicepack / Custom Voice Cloning) ---
        if not self.is_ready():
            raise ModelNotReadyError(self.error_message or "Mô hình VieNeu-TTS chưa sẵn sàng trên CPU.")

        # Kiểm tra chốt chặn hàng đợi CPU: Tối đa 4 request chờ đồng thời trên 2 vCPU
        if not self.cpu_semaphore.acquire(blocking=False):
            logger.warning("Từ chối request: Hàng đợi CPU đã đạt ngưỡng tối đa 4 request.")
            raise CPUQueueFullError("Máy chủ đang bận xử lý tối đa 4 tác vụ âm thanh trên CPU. Vui lòng thử lại sau.")

        try:
            # Tự động chia nhỏ văn bản dài (>350 ký tự) thành các chunk ~250-320 ký tự
            chunks = self.chunk_text(cleaned_text, max_chars=320) if len(cleaned_text) > 350 else [cleaned_text]
            if len(chunks) > 1:
                logger.info(f"Văn bản dài ({len(cleaned_text)} ký tự), tự động chia thành {len(chunks)} chunks để giữ RAM phẳng.")

            # TRƯỜNG HỢP 1: Người dùng upload / ghi âm file mẫu (Custom Voice Cloning trực tiếp)
            if valid_ref_path:
                with self.infer_lock:
                    logger.info(f"Bắt đầu Voice Cloning từ file mẫu người dùng: {valid_ref_path} (Denoise={denoise})")
                    return self._infer_cpu_chunks(chunks, ref_audio=valid_ref_path, denoise=denoise)

            # TRƯỜNG HỢP 2: Sử dụng Custom Voicepacks
            if engine_type == "voicepack":
                vp_engine = get_voicepack_engine()
                sample_path = vp_engine.get_sample_path(voice_id)
                if sample_path and os.path.exists(sample_path):
                    valid_sample = self._validate_ref_audio_path(sample_path)
                    logger.info(f"Định tuyến tới Voicepack: '{voice_info.get('name')}' qua mẫu: {valid_sample}")
                    with self.infer_lock:
                        wav_io = self._infer_cpu_chunks(chunks, ref_audio=valid_sample, denoise=True)
                        if cache_path:
                            self._write_cache(cache_path, wav_io)
                        return wav_io
                else:
                    logger.warning(f"Không tìm thấy file mẫu cho voicepack '{voice_id}', fallback về Hải Đăng")
                    voice_id = "Hải Đăng"

            # TRƯỜNG HỢP 3: VieNeu Presets (25 giọng chuẩn)
            with self.infer_lock:
                logger.info(f"Định tuyến tới VieNeu Engine: '{voice_id}' (Input: '{voice}')")
                wav_io = self._infer_cpu_chunks(chunks, voice=voice_id, denoise=denoise)
                if cache_path:
                    self._write_cache(cache_path, wav_io)
                return wav_io

        finally:
            self.cpu_semaphore.release()

    def _convert_to_wav_io(self, audio_output: Any) -> io.BytesIO:
        if sf is None:
            raise RuntimeError(self.error_message or "Thiếu thư viện 'soundfile' để xuất âm thanh WAV.")

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

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_path = tmp_file.name

            if hasattr(self.tts, "save"):
                self.tts.save(audio_output, tmp_path)
            else:
                raise ValueError("Không thể nhận diện định dạng audio trả về từ VieNeu")

            with open(tmp_path, "rb") as f:
                buffer.write(f.read())
            buffer.seek(0)
            return buffer
        finally:
            if tmp_path and os.path.exists(tmp_path):
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
