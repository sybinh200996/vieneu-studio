// VieNeu-TTS Studio Client Logic
document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const statusBadge = document.getElementById("statusBadge");
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");

    const inputText = document.getElementById("inputText");
    const charCounter = document.getElementById("charCounter");
    const tagButtons = document.querySelectorAll(".tag-btn");

    const tabPresetBtn = document.getElementById("tabPresetBtn");
    const tabCloneBtn = document.getElementById("tabCloneBtn");
    const tabPresetContent = document.getElementById("tabPresetContent");
    const tabCloneContent = document.getElementById("tabCloneContent");

    const voiceSelect = document.getElementById("voiceSelect");
    const dropZone = document.getElementById("dropZone");
    const refAudioInput = document.getElementById("refAudioInput");
    const fileChosenLabel = document.getElementById("fileChosenLabel");

    const recordBtn = document.getElementById("recordBtn");
    const recordBtnIcon = document.getElementById("recordBtnIcon");
    const recordBtnText = document.getElementById("recordBtnText");
    const recordTimer = document.getElementById("recordTimer");
    const previewRecordedAudio = document.getElementById("previewRecordedAudio");

    const denoiseCheckbox = document.getElementById("denoiseCheckbox");
    const generateBtn = document.getElementById("generateBtn");
    const generateIcon = document.getElementById("generateIcon");
    const loadingSpinner = document.getElementById("loadingSpinner");
    const generateBtnText = document.getElementById("generateBtnText");
    const elapsedTimer = document.getElementById("elapsedTimer");

    const playerEmptyState = document.getElementById("playerEmptyState");
    const playerActiveState = document.getElementById("playerActiveState");
    const mainAudioPlayer = document.getElementById("mainAudioPlayer");
    const downloadBtn = document.getElementById("downloadBtn");
    const playerMetaVoice = document.getElementById("playerMetaVoice");
    const playerMetaDuration = document.getElementById("playerMetaDuration");

    const historyList = document.getElementById("historyList");
    const clearHistoryBtn = document.getElementById("clearHistoryBtn");
    const emptyHistoryNotice = document.getElementById("emptyHistoryNotice");

    // State Variables
    let currentMode = "preset"; // "preset" hoặc "clone"
    let selectedFile = null;
    let recordedBlob = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let recordInterval = null;
    let recordSeconds = 0;
    let isRecording = false;
    let sessionHistory = [];

    // --- 1. HEALTH CHECK & LOAD VOICES ---
    async function checkServerHealth() {
        try {
            const res = await fetch("/api/health");
            if (!res.ok) throw new Error("Server trả về lỗi HTTP");
            const data = await res.json();
            
            statusDot.classList.remove("bg-amber-400", "bg-red-500", "animate-ping");
            statusDot.classList.add("bg-emerald-400");
            
            if (data.engine && data.engine.status === "ready") {
                statusText.textContent = `Sẵn sàng (${data.engine.model_name || 'VieNeu'})`;
            } else {
                statusText.textContent = "Server hoạt động (Fallback/Dev)";
            }
        } catch (err) {
            statusDot.classList.remove("bg-amber-400", "bg-emerald-400", "animate-ping");
            statusDot.classList.add("bg-red-500");
            statusText.textContent = "Mất kết nối API";
        }
    }
    checkServerHealth();
    setInterval(checkServerHealth, 30000); // Ping mỗi 30s

    // --- 2. TEXTAREA & CHARACTER COUNTER ---
    inputText.addEventListener("input", () => {
        const len = inputText.value.length;
        charCounter.textContent = `${len} / 2500 ký tự`;
        if (len > 2500) {
            charCounter.classList.add("text-red-400");
        } else {
            charCounter.classList.remove("text-red-400");
        }
    });

    // --- 3. QUICK INSERT EMOTION TAGS AT CARET ---
    tagButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const tag = btn.getAttribute("data-tag");
            const start = inputText.selectionStart;
            const end = inputText.selectionEnd;
            const text = inputText.value;
            
            // Chèn tag vào giữa con trỏ
            inputText.value = text.substring(0, start) + tag + " " + text.substring(end);
            inputText.focus();
            inputText.selectionStart = inputText.selectionEnd = start + tag.length + 1;
            
            // Trigger input event để cập nhật bộ đếm
            inputText.dispatchEvent(new Event("input"));
        });
    });

    // --- 4. TAB SWITCHING ---
    tabPresetBtn.addEventListener("click", () => {
        currentMode = "preset";
        tabPresetBtn.className = "flex-1 pb-3 text-sm font-semibold border-b-2 border-indigo-500 text-indigo-400 flex items-center justify-center gap-2 transition-all";
        tabCloneBtn.className = "flex-1 pb-3 text-sm font-semibold border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center justify-center gap-2 transition-all";
        tabPresetContent.classList.remove("hidden");
        tabCloneContent.classList.add("hidden");
    });

    tabCloneBtn.addEventListener("click", () => {
        currentMode = "clone";
        tabCloneBtn.className = "flex-1 pb-3 text-sm font-semibold border-b-2 border-indigo-500 text-indigo-400 flex items-center justify-center gap-2 transition-all";
        tabPresetBtn.className = "flex-1 pb-3 text-sm font-semibold border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center justify-center gap-2 transition-all";
        tabCloneContent.classList.remove("hidden");
        tabPresetContent.classList.add("hidden");
    });

    // --- 5. DRAG & DROP FILE UPLOAD ---
    dropZone.addEventListener("click", () => refAudioInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("border-indigo-500", "bg-indigo-950/20");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("border-indigo-500", "bg-indigo-950/20");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("border-indigo-500", "bg-indigo-950/20");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    refAudioInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleFileSelection(e.target.files[0]);
        }
    });

    function handleFileSelection(file) {
        selectedFile = file;
        recordedBlob = null; // Ưu tiên file upload nếu chọn mới
        previewRecordedAudio.classList.add("hidden");
        fileChosenLabel.innerHTML = `<span class="text-indigo-400 font-bold">Đã chọn:</span> ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        dropZone.classList.add("border-emerald-500/80", "bg-emerald-950/10");
    }

    // --- 6. MICROPHONE AUDIO RECORDER (MediaRecorder API) ---
    recordBtn.addEventListener("click", async () => {
        if (!isRecording) {
            await startRecording();
        } else {
            stopRecording();
        }
    });

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioChunks = [];
            
            // Tìm MIME type được hỗ trợ tốt nhất trên browser
            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") 
                ? "audio/webm;codecs=opus" 
                : "audio/webm";

            mediaRecorder = new MediaRecorder(stream, { mimeType });
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };

            mediaRecorder.onstop = () => {
                recordedBlob = new Blob(audioChunks, { type: mimeType });
                selectedFile = null; // Đã có file ghi âm
                fileChosenLabel.textContent = "Kéo thả file âm thanh hoặc bấm chọn";
                dropZone.classList.remove("border-emerald-500/80", "bg-emerald-950/10");

                // Preview âm thanh vừa ghi
                const audioURL = URL.createObjectURL(recordedBlob);
                previewRecordedAudio.src = audioURL;
                previewRecordedAudio.classList.remove("hidden");
            };

            mediaRecorder.start(100);
            isRecording = true;
            recordSeconds = 0;
            recordBtn.classList.remove("bg-red-600/80", "hover:bg-red-600");
            recordBtn.classList.add("bg-amber-600", "recording-pulse");
            recordBtnText.textContent = "Dừng ghi âm";
            recordBtnIcon.className = "w-2.5 h-2.5 bg-white rounded-none"; // Vuông = Stop

            recordInterval = setInterval(() => {
                recordSeconds++;
                const mins = String(Math.floor(recordSeconds / 60)).padStart(2, "0");
                const secs = String(recordSeconds % 60).padStart(2, "0");
                recordTimer.textContent = `${mins}:${secs}`;
                
                // Tự động dừng nếu quá 10 giây (khuyến nghị 3-8s)
                if (recordSeconds >= 10) {
                    stopRecording();
                }
            }, 1000);

        } catch (err) {
            alert("Không thể truy cập Microphone: " + err.message + "\nVui lòng cấp quyền micro cho trình duyệt.");
        }
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== "inactive") {
            mediaRecorder.stop();
            mediaRecorder.stream.getTracks().forEach(track => track.stop());
        }
        clearInterval(recordInterval);
        isRecording = false;
        recordBtn.classList.remove("bg-amber-600", "recording-pulse");
        recordBtn.classList.add("bg-red-600/80", "hover:bg-red-600");
        recordBtnText.textContent = "Thu âm lại";
        recordBtnIcon.className = "w-2.5 h-2.5 rounded-full bg-white";
    }

    // --- 7. TTS GENERATE REQUEST ---
    generateBtn.addEventListener("click", async () => {
        const text = inputText.value.trim();
        if (!text) {
            alert("Vui lòng nhập văn bản cần đọc!");
            inputText.focus();
            return;
        }

        const formData = new FormData();
        formData.append("text", text);
        formData.append("denoise", denoiseCheckbox.checked);

        let activeVoiceLabel = voiceSelect.value;

        if (currentMode === "preset") {
            formData.append("voice", voiceSelect.value);
        } else {
            // Voice Clone Mode
            if (recordedBlob) {
                formData.append("ref_audio", recordedBlob, "recorded_sample.webm");
                activeVoiceLabel = "Voice Clone (Micro)";
            } else if (selectedFile) {
                formData.append("ref_audio", selectedFile, selectedFile.name);
                activeVoiceLabel = `Voice Clone (${selectedFile.name})`;
            } else {
                alert("Bạn đang ở chế độ Voice Cloning. Vui lòng tải file mẫu (3-8s) hoặc bấm 'Thu âm trực tiếp' trước!");
                return;
            }
        }

        // Bắt đầu xử lý
        setLoadingState(true);
        const startTime = performance.now();

        try {
            const response = await fetch("/api/tts", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                let errorDetail = "Lỗi tạo âm thanh";
                try {
                    const errJson = await response.json();
                    errorDetail = errJson.detail || errorDetail;
                } catch(e) {}
                throw new Error(errorDetail);
            }

            const blob = await response.blob();
            const elapsedSec = ((performance.now() - startTime) / 1000).toFixed(1);
            const audioUrl = URL.createObjectURL(blob);

            // Cập nhật Player hiển thị
            playerEmptyState.classList.add("hidden");
            playerActiveState.classList.remove("hidden");
            mainAudioPlayer.src = audioUrl;
            mainAudioPlayer.play().catch(() => {}); // Autoplay nếu trình duyệt cho phép

            downloadBtn.href = audioUrl;
            downloadBtn.download = `vieneu_${Date.now()}.wav`;

            playerMetaVoice.textContent = activeVoiceLabel;
            playerMetaDuration.textContent = `Tạo trong: ${elapsedSec}s`;

            // Lưu vào Lịch sử phiên
            addToHistory({
                id: Date.now(),
                text: text,
                voice: activeVoiceLabel,
                url: audioUrl,
                duration: `${elapsedSec}s`,
                timestamp: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })
            });

        } catch (err) {
            alert("Không thể tạo giọng nói: " + err.message);
        } finally {
            setLoadingState(false);
        }
    });

    let elapsedInterval = null;
    function setLoadingState(isLoading) {
        if (isLoading) {
            generateBtn.disabled = true;
            generateIcon.classList.add("hidden");
            loadingSpinner.classList.remove("hidden");
            generateBtnText.textContent = "Đang tổng hợp giọng nói...";
            elapsedTimer.classList.remove("hidden");
            
            let seconds = 0;
            elapsedTimer.textContent = "(0.0s)";
            elapsedInterval = setInterval(() => {
                seconds += 0.1;
                elapsedTimer.textContent = `(${seconds.toFixed(1)}s)`;
            }, 100);
        } else {
            clearInterval(elapsedInterval);
            generateBtn.disabled = false;
            generateIcon.classList.remove("hidden");
            loadingSpinner.classList.add("hidden");
            generateBtnText.textContent = "Tạo âm thanh ngay";
            elapsedTimer.classList.add("hidden");
        }
    }

    // --- 8. SESSION HISTORY MANAGEMENT ---
    function addToHistory(item) {
        sessionHistory.unshift(item);
        renderHistory();
    }

    function renderHistory() {
        if (sessionHistory.length === 0) {
            emptyHistoryNotice.classList.remove("hidden");
            return;
        }
        emptyHistoryNotice.classList.add("hidden");

        historyList.innerHTML = sessionHistory.map(item => `
            <div class="p-3 bg-slate-900/90 rounded-xl border border-slate-800 hover:border-slate-700 transition-all flex flex-col space-y-1.5">
                <div class="flex items-center justify-between text-[11px] text-slate-400">
                    <span class="font-semibold text-indigo-400 truncate max-w-[150px]">${item.voice}</span>
                    <span class="font-mono text-slate-500">${item.timestamp} • ${item.duration}</span>
                </div>
                <p class="text-xs text-slate-200 line-clamp-2 leading-relaxed">"${item.text}"</p>
                <div class="flex items-center justify-end gap-2 pt-1">
                    <button class="play-hist-btn text-[11px] px-2 py-0.5 rounded bg-indigo-600/20 text-indigo-300 hover:bg-indigo-600 hover:text-white transition-all flex items-center gap-1" data-url="${item.url}" data-voice="${item.voice}" data-dur="${item.duration}">
                        Phát
                    </button>
                    <a href="${item.url}" download="vieneu_${item.id}.wav" class="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition-all">
                        Tải WAV
                    </a>
                </div>
            </div>
        `).join("");

        // Gán sự kiện cho các nút phát trong lịch sử
        document.querySelectorAll(".play-hist-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const url = btn.getAttribute("data-url");
                const voice = btn.getAttribute("data-voice");
                const dur = btn.getAttribute("data-dur");

                playerEmptyState.classList.add("hidden");
                playerActiveState.classList.remove("hidden");
                mainAudioPlayer.src = url;
                mainAudioPlayer.play();
                downloadBtn.href = url;
                playerMetaVoice.textContent = voice;
                playerMetaDuration.textContent = dur;
            });
        });
    }

    clearHistoryBtn.addEventListener("click", () => {
        sessionHistory = [];
        historyList.innerHTML = '<p id="emptyHistoryNotice" class="text-xs text-slate-500 text-center py-6">Lịch sử trống</p>';
    });
});
