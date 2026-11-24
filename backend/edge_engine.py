import io
import os
import asyncio
import subprocess
import tempfile
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("EdgeTTSEngine")

# Danh sách các giọng Edge-TTS Neural tiếng Việt chính thức
EDGE_VOICES_METADATA = [
    {
        "id": "vi-VN-HoaiMyNeural",
        "name": "Hoài My (Edge Neural)",
        "gender": "Nữ",
        "region": "Miền Bắc",
        "description": "Nữ · Bắc · Tự nhiên, truyền cảm, tốc độ siêu nhanh (0MB RAM)",
        "style": "Tự nhiên / Tin tức",
        "engine": "edge"
    },
    {
        "id": "vi-VN-NamMinhNeural",
        "name": "Nam Minh (Edge Neural)",
        "gender": "Nam",
        "region": "Miền Bắc",
        "description": "Nam · Bắc · Đĩnh đạc, ấm áp, tốc độ siêu nhanh (0MB RAM)",
        "style": "Tin tức / Thuyết minh",
        "engine": "edge"
    }
]

class EdgeTTSEngine:
    def __init__(self):
        self.sample_rate = 48000

    async def _synthesize_mp3_async(self, text: str, voice: str) -> bytes:
        import edge_tts
        communicate = edge_tts.Communicate(text=text, voice=voice)
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
        return bytes(audio_data)

    def synthesize(self, text: str, voice: str = "vi-VN-HoaiMyNeural") -> io.BytesIO:
        """
        Tổng hợp giọng nói qua Edge Neural Cloud và chuyển đổi sang WAV 48kHz.
        Không tốn RAM trên VPS CPU, tốc độ chỉ ~0.5s - 1s.
        """
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Văn bản tổng hợp không được để trống.")

        # Lấy MP3 bytes từ Edge-TTS
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            mp3_bytes = loop.run_until_complete(self._synthesize_mp3_async(clean_text, voice))
            loop.close()
        except Exception as e:
            logger.error(f"Lỗi khi gọi Edge-TTS: {e}", exc_info=True)
            raise RuntimeError(f"Edge-TTS Error: {e}")

        # Chuyển đổi MP3 sang WAV 48000Hz (PCM 16-bit) qua ffmpeg
        try:
            process = subprocess.Popen(
                ["ffmpeg", "-y", "-i", "pipe:0", "-ar", "48000", "-ac", "1", "-f", "wav", "pipe:1"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            wav_bytes, err = process.communicate(input=mp3_bytes)
            if process.returncode != 0:
                logger.warning(f"ffmpeg cảnh báo: {err.decode(errors='ignore')}")
                # Nếu ffmpeg lỗi, trả về mp3 wrap trong BytesIO làm fallback
                return io.BytesIO(mp3_bytes)
            
            buffer = io.BytesIO(wav_bytes)
            buffer.seek(0)
            return buffer
        except Exception as e:
            logger.warning(f"Không thể gọi ffmpeg chuyển đổi wav, fallback mp3 bytes: {e}")
            buffer = io.BytesIO(mp3_bytes)
            buffer.seek(0)
            return buffer

_edge_instance: Optional[EdgeTTSEngine] = None

def get_edge_engine() -> EdgeTTSEngine:
    global _edge_instance
    if _edge_instance is None:
        _edge_instance = EdgeTTSEngine()
    return _edge_instance
