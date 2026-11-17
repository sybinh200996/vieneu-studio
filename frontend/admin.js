// VieNeu Admin Dashboard Logic
document.addEventListener("DOMContentLoaded", () => {
    // Elements
    const loginScreen = document.getElementById("loginScreen");
    const adminDashboard = document.getElementById("adminDashboard");
    const loginForm = document.getElementById("loginForm");
    const loginUser = document.getElementById("loginUser");
    const loginPass = document.getElementById("loginPass");
    const loginAlert = document.getElementById("loginAlert");
    const loginSubmitBtn = document.getElementById("loginSubmitBtn");
    const loginBtnText = document.getElementById("loginBtnText");

    const adminUsername = document.getElementById("adminUsername");
    const logoutBtn = document.getElementById("logoutBtn");

    // Metrics elements
    const metricsTimestamp = document.getElementById("metricsTimestamp");
    const refreshMetricsBtn = document.getElementById("refreshMetricsBtn");
    const cpuPercent = document.getElementById("cpuPercent");
    const cpuBar = document.getElementById("cpuBar");
    const cpuCores = document.getElementById("cpuCores");

    const ramPercent = document.getElementById("ramPercent");
    const ramBar = document.getElementById("ramBar");
    const ramUsedText = document.getElementById("ramUsedText");
    const ramTotal = document.getElementById("ramTotal");
    const ramAvailText = document.getElementById("ramAvailText");
    const swapText = document.getElementById("swapText");

    const procPid = document.getElementById("procPid");
    const procRss = document.getElementById("procRss");
    const procPeak = document.getElementById("procPeak");
    const procUptime = document.getElementById("procUptime");

    const diskPercent = document.getElementById("diskPercent");
    const diskBar = document.getElementById("diskBar");
    const diskUsedText = document.getElementById("diskUsedText");
    const diskTotal = document.getElementById("diskTotal");
    const diskFreeText = document.getElementById("diskFreeText");

    // Keys elements
    const createKeyForm = document.getElementById("createKeyForm");
    const keyNameInput = document.getElementById("keyNameInput");
    const keysTableBody = document.getElementById("keysTableBody");

    // State
    let token = localStorage.getItem("vieneu_admin_token");
    let username = localStorage.getItem("vieneu_admin_user");
    let metricsTimer = null;

    // --- 1. AUTHENTICATION FLOW ---
    if (token) {
        showDashboard();
    } else {
        showLogin();
    }

    function showLogin() {
        clearInterval(metricsTimer);
        loginScreen.classList.remove("hidden");
        adminDashboard.classList.add("hidden");
    }

    function showDashboard() {
        loginScreen.classList.add("hidden");
        adminDashboard.classList.remove("hidden");
        adminUsername.textContent = username || "Quản trị viên";

        // Tải dữ liệu ban đầu
        fetchMetrics();
        fetchKeys();

        // Tự động làm mới metrics mỗi 3.5 giây
        clearInterval(metricsTimer);
        metricsTimer = setInterval(fetchMetrics, 3500);
    }

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        loginAlert.classList.add("hidden");
        loginSubmitBtn.disabled = true;
        loginBtnText.textContent = "Đang kiểm tra...";

        try {
            const res = await fetch("/api/admin/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username: loginUser.value.trim(),
                    password: loginPass.value.trim()
                })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "Đăng nhập thất bại");
            }

            token = data.token;
            username = data.username;
            localStorage.setItem("vieneu_admin_token", token);
            localStorage.setItem("vieneu_admin_user", username);

            showDashboard();
        } catch (err) {
            loginAlert.textContent = err.message;
            loginAlert.classList.remove("hidden");
        } finally {
            loginSubmitBtn.disabled = false;
            loginBtnText.textContent = "Đăng Nhập Quản Trị";
        }
    });

    logoutBtn.addEventListener("click", async () => {
        try {
            await fetch("/api/admin/logout", {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` }
            });
        } catch(e) {}
        localStorage.removeItem("vieneu_admin_token");
        localStorage.removeItem("vieneu_admin_user");
        token = null;
        username = null;
        showLogin();
    });

    // Helper fetch with auth
    async function authFetch(url, options = {}) {
        options.headers = options.headers || {};
        options.headers["Authorization"] = `Bearer ${token}`;
        const res = await fetch(url, options);
        if (res.status === 401) {
            // Token hết hạn
            logoutBtn.click();
            throw new Error("Phiên làm việc hết hạn");
        }
        return res;
    }

    // --- 2. SYSTEM METRICS ---
    async function fetchMetrics() {
        try {
            const res = await authFetch("/api/admin/metrics");
            if (!res.ok) return;
            const data = await res.json();

            // Timestamp
            metricsTimestamp.textContent = data.timestamp || "--:--:--";

            // CPU
            const cpuVal = data.cpu.percent;
            cpuPercent.textContent = `${cpuVal}%`;
            cpuBar.style.width = `${cpuVal}%`;
            cpuBar.className = getBarColor(cpuVal);
            cpuCores.textContent = `${data.cpu.cores} Cores`;

            // RAM
            const ramVal = data.ram.percent;
            ramPercent.textContent = `${ramVal}%`;
            ramBar.style.width = `${ramVal}%`;
            ramBar.className = getBarColor(ramVal);
            ramUsedText.textContent = `${(data.ram.used_mb / 1024).toFixed(1)} GB dùng`;
            ramTotal.textContent = `${(data.ram.total_mb / 1024).toFixed(1)} GB`;
            ramAvailText.innerHTML = `<span>Khả dụng: <strong>${data.ram.available_mb.toFixed(0)} MB</strong></span><span id="swapText">Swap: ${data.swap.percent}%</span>`;

            // TTS Process
            procPid.textContent = `PID: ${data.tts_process.pid}`;
            procRss.textContent = data.tts_process.rss_mb.toFixed(0);
            procPeak.textContent = `${data.tts_process.peak_mb.toFixed(0)} MB`;
            procUptime.textContent = data.tts_process.uptime_str;

            // Disk
            const diskVal = data.disk.percent;
            diskPercent.textContent = `${diskVal}%`;
            diskBar.style.width = `${diskVal}%`;
            diskBar.className = getBarColor(diskVal);
            diskUsedText.textContent = `${data.disk.used_gb} GB dùng`;
            diskTotal.textContent = `${data.disk.total_gb} GB`;
            diskFreeText.innerHTML = `Trống sẵn sàng: <strong>${data.disk.free_gb} GB</strong>`;

        } catch (e) {
            console.warn("Metrics error:", e);
        }
    }

    function getBarColor(percent) {
        if (percent > 85) return "h-full bg-rose-500 rounded-full transition-all duration-500";
        if (percent > 70) return "h-full bg-amber-500 rounded-full transition-all duration-500";
        return "h-full bg-indigo-500 rounded-full transition-all duration-500";
    }

    refreshMetricsBtn.addEventListener("click", fetchMetrics);

    // --- 3. API KEYS MANAGEMENT ---
    async function fetchKeys() {
        try {
            const res = await authFetch("/api/admin/keys");
            if (!res.ok) return;
            const data = await res.json();
            renderKeysTable(data.keys || []);
        } catch (e) {
            console.warn("Keys error:", e);
        }
    }

    function renderKeysTable(keys) {
        if (keys.length === 0) {
            keysTableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="py-8 text-center text-slate-500">
                        Chưa có API Key nào được tạo. Hãy nhập tên website bên trên để tạo key đầu tiên!
                    </td>
                </tr>
            `;
            return;
        }

        keysTableBody.innerHTML = keys.map(k => `
            <tr class="hover:bg-slate-900/40 transition-colors">
                <td class="py-3.5 px-4 font-semibold text-slate-100 flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full ${k.is_active ? 'bg-emerald-400' : 'bg-slate-600'}"></span>
                    ${escapeHtml(k.name)}
                </td>
                <td class="py-3.5 px-4 font-mono text-[11px] text-indigo-300">
                    <div class="flex items-center gap-2">
                        <span>${k.key.substring(0, 16)}...</span>
                        <button class="copy-key-btn px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all text-[10px]" data-key="${k.key}">
                            Copy
                        </button>
                    </div>
                </td>
                <td class="py-3.5 px-4 font-mono text-[11px] text-slate-400">${k.created_at}</td>
                <td class="py-3.5 px-4 font-mono text-[11px] text-slate-400">${k.last_used_at || 'Chưa dùng'}</td>
                <td class="py-3.5 px-4 text-center font-mono font-bold text-cyan-400">${k.total_requests}</td>
                <td class="py-3.5 px-4 text-center">
                    <button class="toggle-key-btn px-2.5 py-1 rounded-full text-[10px] font-semibold transition-all ${k.is_active ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20' : 'bg-slate-800 text-slate-500 border border-slate-700 hover:text-slate-300'}" data-id="${k.id}">
                        ${k.is_active ? 'Hoạt động' : 'Tạm khóa'}
                    </button>
                </td>
                <td class="py-3.5 px-4 text-right">
                    <button class="delete-key-btn p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors" data-id="${k.id}" data-name="${escapeHtml(k.name)}" title="Xóa vĩnh viễn">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                        </svg>
                    </button>
                </td>
            </tr>
        `).join("");

        // Attach action events
        document.querySelectorAll(".copy-key-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const k = btn.getAttribute("data-key");
                navigator.clipboard.writeText(k);
                const originalText = btn.textContent;
                btn.textContent = "Đã chép!";
                btn.classList.add("bg-emerald-600", "text-white");
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.classList.remove("bg-emerald-600", "text-white");
                }, 1500);
            });
        });

        document.querySelectorAll(".toggle-key-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const id = btn.getAttribute("data-id");
                await authFetch(`/api/admin/keys/${id}/toggle`, { method: "PUT" });
                fetchKeys();
            });
        });

        document.querySelectorAll(".delete-key-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const id = btn.getAttribute("data-id");
                const name = btn.getAttribute("data-name");
                if (confirm(`Bạn có chắc chắn muốn xóa API Key của "${name}" không? Các website đang dùng key này sẽ không thể kết nối được nữa.`)) {
                    await authFetch(`/api/admin/keys/${id}`, { method: "DELETE" });
                    fetchKeys();
                }
            });
        });
    }

    createKeyForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = keyNameInput.value.trim();
        if (!name) return;

        try {
            const res = await authFetch("/api/admin/keys", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name })
            });
            if (res.ok) {
                keyNameInput.value = "";
                fetchKeys();
            }
        } catch (e) {
            alert("Lỗi tạo key: " + e.message);
        }
    });

    // --- 4. SNIPPET TABS ---
    const snippetTabs = document.querySelectorAll(".snippet-tab");
    const snippetBlocks = document.querySelectorAll(".snippet-block");

    snippetTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const targetId = tab.getAttribute("data-target");

            snippetTabs.forEach(t => {
                t.className = "snippet-tab text-slate-400 hover:text-slate-200 pb-1 px-2";
            });
            tab.className = "snippet-tab text-indigo-400 border-b-2 border-indigo-500 pb-1 px-2";

            snippetBlocks.forEach(b => {
                if (b.id === targetId) {
                    b.classList.remove("hidden");
                } else {
                    b.classList.add("hidden");
                }
            });
        });
    });

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
});
