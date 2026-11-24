import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("VoicepackEngine")

VOICEPACKS_DIR = Path(__file__).resolve().parent / "voicepacks"
MANIFEST_FILE = VOICEPACKS_DIR / "manifest.json"

DEFAULT_VOICEPACKS = [
    {
        "id": "VP_MC_Nam",
        "name": "MC Thời Sự Nam (Voicepack)",
        "gender": "Nam",
        "region": "Miền Bắc",
        "description": "Nam · Bắc · Phát thanh truyền hình chuẩn, dõng dạc",
        "style": "Tin tức / MC",
        "sample_file": "mc_vtv_nam.wav",
        "engine": "voicepack"
    },
    {
        "id": "VP_MC_Nu",
        "name": "MC Thời Sự Nữ (Voicepack)",
        "gender": "Nữ",
        "region": "Miền Bắc",
        "description": "Nữ · Bắc · Sang trọng, truyền cảm, tin tức thời sự",
        "style": "Tin tức / MC",
        "sample_file": "mc_vtv_nu.wav",
        "engine": "voicepack"
    },
    {
        "id": "VP_KeChuyenDem",
        "name": "Kể Chuyện Đêm (Voicepack)",
        "gender": "Nam",
        "region": "Miền Bắc",
        "description": "Nam · Bắc · Trầm ấm, sâu lắng, đọc truyện đêm khuya",
        "style": "Kể chuyện / Audio Book",
        "sample_file": "ke_chuyen_dem.wav",
        "engine": "voicepack"
    },
    {
        "id": "VP_NuHue",
        "name": "Nữ Huế Thơ Mộng (Voicepack)",
        "gender": "Nữ",
        "region": "Miền Trung",
        "description": "Nữ · Trung (Huế) · Dịu dàng, đằm thắm, ngọt ngào",
        "style": "Thơ mộng / Thuyết minh",
        "sample_file": "nu_hue.wav",
        "engine": "voicepack"
    },
    {
        "id": "VP_NuMienTay",
        "name": "Nữ Miền Tây (Voicepack)",
        "gender": "Nữ",
        "region": "Miền Nam",
        "description": "Nữ · Nam (Miền Tây) · Ngọt ngào, mộc mạc, gần gũi",
        "style": "Kể chuyện / Tâm tình",
        "sample_file": "nu_mientay.wav",
        "engine": "voicepack"
    },
    {
        "id": "VP_ReviewPhim",
        "name": "Review Phim Hào Hứng (Voicepack)",
        "gender": "Nam",
        "region": "Miền Nam",
        "description": "Nam · Nam · Nhanh, sôi nổi, phong cách tóm tắt phim",
        "style": "Review / TikTok",
        "sample_file": "review_phim.wav",
        "engine": "voicepack"
    }
]

class VoicepackEngine:
    def __init__(self):
        self.voicepacks: List[Dict[str, Any]] = []
        self._init_voicepacks()

    def _init_voicepacks(self):
        VOICEPACKS_DIR.mkdir(parents=True, exist_ok=True)
        if not MANIFEST_FILE.exists():
            try:
                with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_VOICEPACKS, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Không thể ghi manifest.json: {e}")

        # Đọc từ manifest nếu có
        try:
            if MANIFEST_FILE.exists():
                with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                    self.voicepacks = json.load(f)
            else:
                self.voicepacks = DEFAULT_VOICEPACKS
        except Exception as e:
            logger.warning(f"Lỗi đọc manifest.json: {e}")
            self.voicepacks = DEFAULT_VOICEPACKS

    def get_voicepacks(self) -> List[Dict[str, Any]]:
        return self.voicepacks

    def get_sample_path(self, voice_id: str) -> Optional[str]:
        for vp in self.voicepacks:
            if vp["id"].lower() == voice_id.lower() or vp["name"].lower() == voice_id.lower():
                sample_file = vp.get("sample_file")
                if sample_file:
                    target = VOICEPACKS_DIR / sample_file
                    if target.exists():
                        return str(target)

        # Fallback tìm trong thư mục samples của vieneu nếu có
        try:
            import vieneu
            pkg_dir = Path(vieneu.__file__).parent
            samples_dir = pkg_dir / "assets" / "samples"
            if samples_dir.exists():
                for wav_file in samples_dir.glob("*.wav"):
                    return str(wav_file)
        except Exception:
            pass

        return None

_voicepack_instance: Optional[VoicepackEngine] = None

def get_voicepack_engine() -> VoicepackEngine:
    global _voicepack_instance
    if _voicepack_instance is None:
        _voicepack_instance = VoicepackEngine()
    return _voicepack_instance
