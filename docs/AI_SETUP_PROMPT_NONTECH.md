# Hướng Dẫn Cài Đặt 1-Shot Cho Người Không Chuyên Kỹ Thuật (Non-Tech)

Tài liệu này giúp bất kỳ nhân sự không chuyên kỹ thuật nào (Kinh doanh, Sản phẩm, Nhân sự, Kế toán, Truyền thông, Trợ lý, Ban Giám Đốc) cài đặt xong **LLM Provider Router** chỉ bằng **1 lần dán (1-Shot Prompt)** vào trợ lý AI (Antigravity, Claude, Cursor, Codex, GitHub Copilot).

---

## Phần 1: Prompt Ngắn (1-Shot Online)

Sao chép nguyên văn khung bên dưới, thay `<PROXY_URL>` và `<YOUR_API_KEY>` bằng thông tin được cấp riêng, rồi dán **một lần duy nhất** vào trợ lý AI trên máy tính của bạn:

```text
Bạn là trợ lý kỹ thuật toàn quyền trên máy tính này. Tôi KHÔNG rành lập trình (non-tech).
Hãy tự động đọc hướng dẫn chuẩn tại:
https://raw.githubusercontent.com/productaivn-wq/llm-provider-router/main/docs/AI_SETUP_PROMPT_NONTECH.md
và thực hiện ĐẦY ĐỦ từ Phase 1 đến Phase 7 trong 1 lượt duy nhất để máy tôi cài xong và chạy được AI nội bộ.

Thông tin kết nối của tôi:
- Địa chỉ máy chủ: <PROXY_URL>
- Mã khóa riêng: <YOUR_API_KEY>

Quy tắc bắt buộc:
- KHÔNG hỏi tôi gõ lệnh hay tự sửa lỗi kỹ thuật; tự kiểm tra và tự xử lý mọi bước (kể cả cài Python nếu thiếu hoặc tải file ZIP nếu thiếu git).
- KHÔNG in hoặc lưu công khai mã khóa riêng ra màn hình.
- Sau khi kiểm tra chạy thật thành công, chỉ trả lời ngắn gọn bằng tiếng Việt dễ hiểu theo đúng mẫu ở Phase 7.
```

---

## Phần 2: Runbook Tự Hành Đầy Đủ 7 Phase (Dành Cho Trợ Lý AI — Hoạt Động Cả Khi Offline / Không Đọc Web)

```text
[1-SHOT AUTONOMOUS SETUP RUNBOOK — NON-TECH USER]
Proxy URL: <PROXY_URL>
Personal Key: <YOUR_API_KEY>

### GOLDEN RULE (BẮT BUỘC TUÂN THỦ)
The user is NON-TECHNICAL.
- NEVER ask the user to open a terminal, run shell commands, edit files, adjust PowerShell ExecutionPolicy, or troubleshoot Python/Git/pip errors.
- Execute every phase autonomously from start to finish in ONE run, self-healing recoverable errors silently.
- NEVER echo, log, or print `<YOUR_API_KEY>` in command output or final user-facing messages.
- Reply at the end in warm, plain, jargon-free Vietnamese.

---

### Phase 1: Detect OS, Normalize UTF-8 & Pick Safe Workspace
1. Detect OS (`Windows`, `macOS`, or `Linux`).
2. Set `PYTHONUTF8=1` for all Python invocations so Vietnamese text never fails with `cp1252` encoding errors.
3. Choose the clean non-system workspace directory:
   - Windows: `%USERPROFILE%\llm-provider-router` (expand `%USERPROFILE%`, do NOT use `System32` or `Temp`).
   - macOS / Linux: `~/llm-provider-router` (expand `$HOME`).

### Phase 2: Probe or Auto-Install Python 3.10+
1. Probe Python candidates in order:
   - Windows: `py -3`, `python3`, `python`, plus `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`, `%LOCALAPPDATA%\Programs\Python\Python311\python.exe`.
   - macOS / Linux: `python3`, `python`, `/opt/homebrew/bin/python3`, `/usr/local/bin/python3`.
2. Verify the candidate actually runs and reports `sys.version_info >= (3, 10)` AND is NOT the Windows Store `WindowsApps` stub (`WindowsApps\python.exe` that exits 9009 or prints Microsoft Store prompt).
3. If NO valid Python 3.10+ exists, auto-install silently without bothering the user:
   - Windows: `winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent`
     Then refresh executable lookup (check `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` and `%ProgramFiles%\Python312\python.exe`).
   - macOS: `brew install python@3.12` (or if Homebrew is missing, install Python pkg / Xcode CLT cleanly).
   - Linux: `sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip` (or `dnf install -y python3`).
4. Confirm `<PYTHON_EXE> --version` is Python 3.10+.

### Phase 3: Acquire `llm-provider-router` Repository (With Zero-Git ZIP Fallback)
1. Check if the target workspace folder already has `pyproject.toml`:
   - If `git` exists and `.git` is present, run `git pull --ff-only`.
   - Else if `git` exists and target folder does not exist, run:
     `git clone https://github.com/productaivn-wq/llm-provider-router.git "<TARGET_DIR>"`
2. If `git` is missing or blocked on the machine (common on Non-Tech laptops):
   - Download `https://github.com/productaivn-wq/llm-provider-router/archive/refs/heads/main.zip` using Python `urllib.request` (or PowerShell `Invoke-WebRequest` / `curl`).
   - Extract the archive with Python `zipfile` into the parent directory.
   - Move/rename extracted folder `llm-provider-router-main` -> `llm-provider-router` (`<TARGET_DIR>`).
3. Verify `<TARGET_DIR>\pyproject.toml` exists.

### Phase 4: ExecutionPolicy-Safe Isolated Virtualenv Install
- IMPORTANT (Windows Safety): **NEVER** run `.venv\Scripts\Activate.ps1` (it fails on machines with `Restricted` PowerShell ExecutionPolicy).
- Always invoke the virtualenv Python binary directly:
  - Windows: `<VENV_PY>` = `<TARGET_DIR>\.venv\Scripts\python.exe`
  - macOS / Linux: `<VENV_PY>` = `<TARGET_DIR>/.venv/bin/python`
1. Create virtualenv if missing: `<PYTHON_EXE> -m venv "<TARGET_DIR>\.venv"` (or `/.venv`).
2. Upgrade pip silently if needed and install editable package:
   `"<VENV_PY>" -m pip install --upgrade pip`
   `"<VENV_PY>" -m pip install -e "<TARGET_DIR>"`

### Phase 5: Zero-Leak Cross-Platform Key Configuration
Configure `.env` via Python `subprocess.run(..., input=API_KEY, text=True)` so there are ZERO shell-escaping bugs, ZERO newline corruptions, and ZERO command-history or stdout leaks:

```python
import subprocess
api_key = """<YOUR_API_KEY>""".strip()
proxy_url = """<PROXY_URL>""".strip()
res = subprocess.run(
    [
        VENV_PY, "-m", "llm_provider_router", "setup",
        "--url", proxy_url,
        "--api-key-stdin",
        "--model", "chatgpt/gpt-5.3-instant",
        "--coding-model", "chatgpt/gpt-5.3-codex",
        "--user-agent", "LLM-Provider-Router/1.0",
        "--env-file", ENV_FILE_PATH,
        "--probe",
        "--json",
    ],
    cwd=TARGET_DIR,
    input=api_key,
    text=True,
    capture_output=True,
    check=False,
)
```
Assert `res.returncode == 0` and parsed JSON has `"ok": true`.

### Phase 6: End-to-End Verification & Self-Healing
Run all 3 live checks using `VENV_PY` (NEVER expose raw keys):
1. `<VENV_PY> -m llm_provider_router probe --env-file "<ENV_FILE_PATH>" --json` -> check `"ok": true` and record `models_count`.
2. `<VENV_PY> -m llm_provider_router models --env-file "<ENV_FILE_PATH>" --json` -> check `"count" >= 1`.
3. `<VENV_PY> -m llm_provider_router chat "Tra loi dung 2 chu: KET NOI OK" --env-file "<ENV_FILE_PATH>" --json` -> check `"ok": true` and non-empty `"content"`.

Self-Healing Rules if any check fails:
- **HTTP 403 / Cloudflare 1010**: Re-run `setup` ensuring `--user-agent LLM-Provider-Router/1.0` is saved in `.env`, then re-run `probe --json`.
- **HTTP 401 Unauthorized**: Strip hidden whitespace, quotes, or CR/LF from `<YOUR_API_KEY>`, re-run Phase 5 `setup` cleanly via `subprocess.run(..., input=cleaned_key)`, and retry `probe --json`.
- **Timeout / Temporary Proxy Hiccup**: Clear cooldowns via `<VENV_PY> -m llm_provider_router reset-cooldowns --env-file "<ENV_FILE_PATH>"` and retry once with `--timeout 20`.
- **Port 18766 Busy**: Check if `127.0.0.1:18766` is already serving `llm-router` (`GET /v1/models` == 200); if another process holds `18766`, use port `18767` in the launcher and update `ROUTER_GATEWAY_PORT=18767`.

### Phase 7: Create 1-Click Daily Launcher, Test Local Gateway & Reply in Plain Vietnamese
1. Generate a 1-click launcher in `<TARGET_DIR>` (and optionally copy a shortcut or file link for the user):
   - Windows `<TARGET_DIR>\Mo_Cong_AI.bat`:
     ```bat
     @echo off
     title Cong AI Noi Bo (Dang hoat dong - khong tat cua so nay khi dang dung AI)
     cd /d "%~dp0"
     echo Dang khoi dong Cong AI cuc bo tai http://127.0.0.1:18766/v1 ...
     ".venv\Scripts\python.exe" -m llm_provider_router serve
     pause
     ```
   - macOS / Linux `<TARGET_DIR>/Mo_Cong_AI.command` (`chmod +x`):
     ```bash
     #!/usr/bin/env bash
     cd "$(dirname "$0")"
     echo "Dang khoi dong Cong AI cuc bo tai http://127.0.0.1:18766/v1 ..."
     exec "./.venv/bin/python" -m llm_provider_router serve
     ```
2. Start the gateway briefly in a background process, verify `GET http://127.0.0.1:<PORT>/v1/models` returns HTTP `200`, then stop the temporary verification process if you are handing over the launcher (or keep it running if the user's AI IDE is actively connecting right now).
3. Detect if the user's current app supports OpenAI-compatible settings (Antigravity, Cursor, Continue, Cline, ChatBox, etc.) and configure or print simple 3-line copy fields:
   - Địa chỉ kết nối: `http://127.0.0.1:<PORT>/v1`
   - Mã kết nối nội bộ: `local-router`
   - Mô hình mặc định: `router/auto`
4. Reply to the user in **plain, reassuring Vietnamese** (zero dev jargon, zero raw key):
   - Xác nhận đã cài đặt và kiểm tra kết nối thật thành công (`<models_count>` mô hình AI sẵn sàng, câu trả lời thử nghiệm thành công).
   - Chỉ đường dẫn thư mục cài đặt và file bấm 1 lần `Mo_Cong_AI.bat` (hoặc `Mo_Cong_AI.command`).
   - Hiển thị 3 thông tin kết nối gọn gàng cho ứng dụng AI hằng ngày.
```
