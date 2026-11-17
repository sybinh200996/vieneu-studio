#!/usr/bin/env bash
# ==============================================================================
# SCRIPT TỰ ĐỘNG THIẾT LẬP DỰ ÁN VIENEU-TTS STUDIO TRÊN LINUX UBUNTU VPS (CPU)
# ==============================================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================================${NC}"
echo -e "${BLUE}  BẮT ĐẦU CÀI ĐẶT DỰ ÁN VIENEU-TTS STUDIO WEB APP TRÊN UBUNTU VPS  ${NC}"
echo -e "${BLUE}==================================================================${NC}"

# 1. Cài đặt các gói hệ thống cần thiết
echo -e "\n${YELLOW}[1/4] Đang cập nhật hệ thống và cài đặt thư viện âm thanh (libsndfile, ffmpeg)...${NC}"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip libsndfile1 ffmpeg git curl

# 2. Tạo môi trường ảo Python
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo -e "\n${YELLOW}[2/4] Đang khởi tạo môi trường ảo Python (venv) tại: ${PROJECT_DIR}/venv...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}Đã tạo venv thành công.${NC}"
else
    echo -e "${GREEN}Môi trường ảo venv đã tồn tại, tiếp tục.${NC}"
fi

source venv/bin/activate
pip install --upgrade pip

# 3. Cài đặt các thư viện Python
echo -e "\n${YELLOW}[3/4] Đang cài đặt các thư viện Python từ backend/requirements.txt...${NC}"
if pip install -r backend/requirements.txt; then
    echo -e "${GREEN}Cài đặt requirements.txt thành công.${NC}"
else
    echo -e "${YELLOW}Phát hiện lỗi build llama-cpp, đang thử cài vieneu với pre-built CPU wheel...${NC}"
    pip install vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/
    pip install fastapi uvicorn[standard] python-multipart soundfile numpy pydantic
fi

# 4. Tiền tải trọng số mô hình (Pre-download model weights) để tránh trễ ở request đầu tiên
echo -e "\n${YELLOW}[4/4] Đang tiền tải trọng số mô hình VieNeu-TTS về cache VPS...${NC}"
python3 -c "
try:
    from vieneu import Vieneu
    print('Đang tải và kiểm tra mô hình VieNeu...')
    tts = Vieneu()
    print('Pre-download hoàn tất thành công!')
except Exception as e:
    print(f'Ghi chú khi pre-download: {e}')
" || echo -e "${YELLOW}Model sẽ tự động tải ở lần suy luận đầu tiên.${NC}"

echo -e "\n${GREEN}==================================================================${NC}"
echo -e "${GREEN}  CÀI ĐẶT HOÀN TẤT! SẴN SÀNG KHỞI CHẠY BẰNG PM2 HOẶC UVICORN.       ${NC}"
echo -e "${GREEN}  - Chạy thử nghiệm: source venv/bin/activate && uvicorn backend.app:app --host 0.0.0.0 --port 8005${NC}"
echo -e "${GREEN}  - Chạy production: pm2 start ecosystem.config.js               ${NC}"
echo -e "${GREEN}==================================================================${NC}"
