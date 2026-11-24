// Cấu hình PM2 Process Manager cho VieNeu-TTS Studio
module.exports = {
  apps: [
    {
      name: "vieneu-studio",
      // Chạy uvicorn trực tiếp từ virtualenv để đảm bảo đúng môi trường python
      script: "./venv/bin/uvicorn",
      args: "backend.app:app --host 127.0.0.1 --port 8005 --workers 1",
      cwd: __dirname,
      interpreter: "none",
      autorestart: true,
      watch: false,
      // Tự động khởi động lại nếu tiến trình ngốn quá 2200MB RAM (chốt chặn an toàn cho VPS 4GB)
      max_memory_restart: "2200M",
      env: {
        NODE_ENV: "production",
        PYTHONUNBUFFERED: "1",
        VIENEU_MODEL: "v3turbo",     // Hoặc 'v3nano' nếu VPS ít RAM
        VIENEU_PRECISION: "int8",     // Ép int8 để suy luận nhanh nhất trên CPU
        VIENEU_DEVICE: "cpu"
      },
      // Ghi log chuẩn
      error_file: "./logs/pm2-error.log",
      out_file: "./logs/pm2-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      merge_logs: true
    }
  ]
};
