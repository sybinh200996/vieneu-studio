import io
import os
import asyncio
import concurrent.futures
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

    @staticmethod
    def _normalize_text_for_edge(text: str) -> str:
        """
        Chuẩn hóa văn bản tương thích ngữ âm cho Microsoft Edge-TTS.
        Khắc phục lỗi G2P tokenizer của Azure Speech đối với các âm tiết s+y dài.
        """
        import re
        norm_map = {
            r'\bSỹ\b': 'Sĩ',
            r'\bsỹ\b': 'sĩ',
            r'\bSy\b': 'Si',
            r'\bsy\b': 'si',
            r'\bSý\b': 'Sí',
            r'\bsý\b': 'sí',
            r'\bSỳ\b': 'Sì',
            r'\bsỳ\b': 'sì',
            r'\bSỷ\b': 'Sỉ',
            r'\bsỷ\b': 'sỉ',
            r'\bSỵ\b': 'Sị',
            r'\bsỵ\b': 'sị',
        }
        res = text
        for pat, rep in norm_map.items():
            res = re.sub(pat, rep, res)
        return res

    def synthesize(self, text: str, voice: str = "vi-VN-HoaiMyNeural") -> io.BytesIO:
        """
        Tổng hợp giọng nói qua Edge Neural Cloud và chuyển đổi sang WAV 48kHz.
        Không tốn RAM trên VPS CPU, tốc độ chỉ ~0.5s - 1s.
        """
        clean_text = self._normalize_text_for_edge(text.strip())
        if not clean_text:
            raise ValueError("Văn bản tổng hợp không được để trống.")

        # Lấy MP3 bytes từ Edge-TTS trong Thread riêng biệt để tránh xung đột event loop FastAPI
        try:
            def runner():
                thread_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(thread_loop)
                try:
                    return thread_loop.run_until_complete(self._synthesize_mp3_async(clean_text, voice))
                finally:
                    thread_loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                mp3_bytes = executor.submit(runner).result(timeout=60)
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
