# VieNeu-TTS Studio Web App (CPU Optimized)

Ứng dụng Web độc lập (Self-hosted Web App) phục vụ tổng hợp và nhân bản giọng nói tiếng Việt chất lượng cao (48kHz), tối ưu hóa vận hành mượt mà trên máy chủ **Linux Ubuntu VPS (chỉ dùng CPU, không cần GPU)** dựa trên nền tảng **VieNeu-TTS (ONNX Runtime int8)**.

---

## 1. Cấu Trúc Dự Án

```text
vieneu-studio/
├── backend/
│   ├── app.py                # FastAPI server chính & StaticFiles mount
│   ├── tts_engine.py         # Engine TTS Singleton, Thread-safe Lock, int8 CPU
│   └── requirements.txt      # Thư viện Python phụ thuộc
├── frontend/
│   ├── index.html            # Giao diện Studio Dark Mode hiện đại (Tailwind CSS)
│   └── app.js                # Xử lý logic, ghi âm Micro, Audio Player, Lịch sử
├── scripts/
│   ├── setup_vps.sh          # Script tự động cài đặt môi trường trên Ubuntu VPS
│   └── nginx_vieneu.conf     # Cấu hình mẫu Nginx Reverse Proxy (25MB, 300s timeout)
├── ecosystem.config.js       # File cấu hình PM2 Process Manager (1 worker, 2GB RAM restart)
└── README.md                 # Tài liệu hướng dẫn chi tiết
```

---

## 2. Tính Năng Nổi Bật

- **Tối ưu 100% cho CPU VPS:** Chạy qua ONNX Runtime lượng tử hóa `int8` (hoặc `v3nano`), tiết kiệm RAM và giảm tối đa độ trễ.
- **An toàn luồng (Thread-safe):** Bọc hàng đợi suy luận bằng `threading.Lock()` tại tầng Singleton, triệt tiêu nguy cơ nghẽn CPU hoặc sập RAM khi có nhiều request đồng thời.
- **2 Chế độ linh hoạt:**
  1. *Giọng đọc có sẵn:* Hỗ trợ đủ vùng miền Bắc - Trung - Nam (Hải Đăng, Ngọc, Bình, Đoan, Tuyên, Mai...).
  2. *Voice Cloning tức thì:* Nhân bản giọng nói từ file mẫu 3-8 giây hoặc thu âm trực tiếp qua Micro ngay trên trình duyệt.
- **Hỗ trợ thẻ biểu cảm:** Chèn nhanh `[cười]`, `[thở dài]`, `[hắng giọng]`, `[ngạc nhiên]`, `[ngập ngừng]` vào câu đọc.
- **Tự động dọn rác:** Cơ chế giải phóng và xóa file tạm ngay trong khối `finally` không làm đầy ổ cứng máy chủ.
- **Giao diện Studio Dark Theme:** Tinh tế, có audio player tùy chỉnh, bộ đếm thời gian tạo thực tế và lịch sử phiên làm việc.

---

## 3. Hướng Dẫn Triển Khai Trên Ubuntu VPS

### Bước 1: Sao chép mã nguồn lên VPS
Tạo thư mục và đưa toàn bộ mã nguồn vào `/var/www/vieneu-studio`:
```bash
sudo mkdir -p /var/www/vieneu-studio
sudo chown -R $USER:$USER /var/www/vieneu-studio
cd /var/www/vieneu-studio
```

### Bước 2: Chạy script tự động cài đặt
Cấp quyền thực thi và chạy `scripts/setup_vps.sh`:
```bash
chmod +x scripts/setup_vps.sh
./scripts/setup_vps.sh
```
Script sẽ tự động:
- Cài đặt `libsndfile1`, `ffmpeg`, `python3-venv`.
- Tạo môi trường ảo `venv` và cài đặt `requirements.txt`.
- Tải trước trọng số mô hình VieNeu-TTS.

### Bước 3: Cấu hình PM2 để chạy nền tự động
Cài đặt PM2 (nếu máy chủ chưa có NodeJS/PM2):
```bash
# Cài đặt NodeJS & PM2 (nếu chưa có)
sudo apt install -y nodejs npm
sudo npm install -g pm2

# Khởi chạy ứng dụng
mkdir -p logs
pm2 start ecosystem.config.js

# Cấu hình tự động khởi động cùng hệ điều hành
pm2 save
pm2 startup
```

Kiểm tra trạng thái tiến trình:
```bash
pm2 status
pm2 logs vieneu-studio
```

---

## 4. Cấu Hình Nginx & Tên Miền (Domain / SSL)

### Cài đặt Nginx:
```bash
sudo apt install -y nginx
```

### Thiết lập Server Block:
```bash
sudo cp scripts/nginx_vieneu.conf /etc/nginx/sites-available/vieneu-studio
sudo nano /etc/nginx/sites-available/vieneu-studio
# Thay your-domain.com bằng tên miền hoặc địa chỉ IP VPS của bạn
```

Kích hoạt và nạp lại Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/vieneu-studio /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### (Tùy chọn) Cấp chứng chỉ SSL miễn phí bằng Let's Encrypt:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## 5. Kiểm Thử Hệ Thống (Testing)

### Kiểm tra sức khỏe (Health Check):
```bash
curl http://127.0.0.1:8005/api/health
```
Kết quả trả về:
```json
{
  "app": "VieNeu-TTS Studio",
  "version": "1.0.0",
  "engine": {
    "status": "ready",
    "model_name": "v3turbo",
    "precision": "int8",
    "device": "cpu",
    "sample_rate": 48000
  }
}
```

### Kiểm tra danh sách giọng đọc:
```bash
curl http://127.0.0.1:8005/api/voices
```

### Kiểm tra tạo giọng đọc bằng CLI:
```bash
curl -X POST "http://127.0.0.1:8005/api/tts" \
  -F "text=Xin chào, tôi là trợ lý ảo VieNeu-TTS Studio." \
  -F "voice=Hải Đăng" \
  --output test_speech.wav
```

---

## 6. Xử Lý Sự Cố & Tối Ưu Thêm

1. **VPS có 1GB - 2GB RAM:**
   - Trong file `ecosystem.config.js`, đổi `VIENEU_MODEL: "v3nano"` để mô hình nhẹ hơn và tốn ít RAM hơn.
   - Thêm Swap file nếu máy chủ chưa có Swap:
     ```bash
     sudo fallocate -l 2G /swapfile
     sudo chmod 600 /swapfile
     sudo mkswap /swapfile
     sudo swapon /swapfile
     ```
2. **Lỗi Upload file mẫu bị chặn 413 (Request Entity Too Large):**
   - Đảm bảo dòng `client_max_body_size 25M;` đã có trong file cấu hình Nginx.
3. **Lỗi 504 Gateway Timeout khi đọc văn bản dài:**
   - Đảm bảo cấu hình `proxy_read_timeout 300s;` trong Nginx.
