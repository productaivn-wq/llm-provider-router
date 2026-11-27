# Hướng Dẫn Cài Đặt 1-Shot Cho Người Không Chuyên Kỹ Thuật (Non-Tech)

Tài liệu này giúp bất kỳ nhân sự không chuyên kỹ thuật nào (Kinh doanh, Sản phẩm, Nhân sự, Kế toán, Truyền thông, Trợ lý, Ban Giám Đốc) cài đặt xong **LLM Provider Router**, bật sẵn trang **Web Chat AI tiếng Việt** (`Mo_Chat_AI`) và kết nối trợ lý AI chỉ bằng **1 lần dán (1-Shot Prompt)**.

Xem giải thích trực quan ("Cài để làm gì & Làm gì tiếp theo?"): [docs/VISUAL_GUIDE_VI.md](VISUAL_GUIDE_VI.md)

---

## Phần 1: Prompt Ngắn (1-Shot Online)

Sao chép nguyên văn khung bên dưới, thay `<PROXY_URL>` và `<YOUR_API_KEY>` bằng thông tin được cấp riêng, rồi dán **một lần duy nhất** vào trợ lý AI trên máy tính của bạn:

```text
Bạn là trợ lý kỹ thuật toàn quyền trên máy tính này. Tôi KHÔNG rành lập trình (non-tech).
Hãy tự động đọc hướng dẫn chuẩn tại:
https://raw.githubusercontent.com/productaivn-wq/llm-provider-router/main/docs/AI_SETUP_PROMPT_NONTECH.md
và thực hiện ĐẦY ĐỦ từ Phase 1 đến Phase 7 trong 1 lượt duy nhất để máy tôi cài xong, bật sẵn cổng AI nền, tạo nút bấm Mo_Chat_AI và kiểm tra mở được trang Chat AI tại http://127.0.0.1:18766/.

Thông tin kết nối của tôi:
- Địa chỉ máy chủ: <PROXY_URL>
- Mã khóa riêng: <YOUR_API_KEY>

Quy tắc bắt buộc:
- KHÔNG hỏi tôi gõ lệnh hay tự sửa lỗi kỹ thuật; tự xử lý mọi lỗi UTF-8/BOM, Python, hoặc git.
- KHÔNG in hoặc làm lộ mã khóa riêng ra màn hình.
- Sau khi chạy xong `connect --start-gateway`, hãy trình bày thật trực quan bằng tiếng Việt đơn giản: công cụ này dùng để làm gì, nút bấm mở trang Chat AI ở đâu, công cụ nào đã tự gắn và 3 dòng cấu hình nếu tôi muốn gắn vào app AI khác.
```

---

## Phần 2: Runbook Tự Hành Đầy Đủ 7 Phase (Dành Cho Trợ Lý AI — Hoạt Động Cả Khi Offline / Không Đọc Web)

```text
[1-SHOT AUTONOMOUS SETUP & AUTO-CONNECT RUNBOOK — NON-TECH USER]
Proxy URL: <PROXY_URL>
Personal Key: <YOUR_API_KEY>

### GOLDEN RULE (BẮT BUỘC TUÂN THỦ)
The user is NON-TECHNICAL.
- NEVER ask the user to open a terminal, run shell commands, edit files, adjust PowerShell ExecutionPolicy, or troubleshoot UTF-8/Python/Git/pip errors.
- Execute every phase autonomously in ONE pass.
- NEVER echo, log, or print `<YOUR_API_KEY>` in command output or user-facing messages.
- Reply at the end in warm, plain, visual Vietnamese explaining: WHY it is installed, WHERE to click `Mo_Chat_AI` / `http://127.0.0.1:18766/`, and WHAT was auto-connected vs 3-field GUI instructions.

---

### Phase 1: Force UTF-8 Environment & Pick Clean Workspace
1. Detect OS (`Windows`, `macOS`, or `Linux`).
2. Always force UTF-8 before running Python/PowerShell commands:
   - Windows PowerShell: `[Console]::InputEncoding = [Console]::OutputEncoding = $OutputEncoding = [System.Text.UTF8Encoding]::new($false)` and `$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"`
   - POSIX shell: `export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 LANG=C.UTF-8`
3. Target folder:
   - Windows: `%USERPROFILE%\llm-provider-router` (do NOT use `System32` or `Temp`).
   - macOS / Linux: `~/llm-provider-router`.

### Phase 2: Probe or Auto-Install Python 3.10+
1. Probe Python candidates:
   - Windows: `py -3`, `python3`, `python`, `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`, `%LOCALAPPDATA%\Programs\Python\Python311\python.exe`.
   - macOS / Linux: `python3`, `python`, `/opt/homebrew/bin/python3`, `/usr/local/bin/python3`.
2. Verify `sys.version_info >= (3, 10)` and reject Windows Store `WindowsApps` stubs.
3. If no valid Python 3.10+ exists, install silently (`winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent` on Windows, `brew install python@3.12` on macOS, or `apt`/`dnf` on Linux) and refresh lookup.

### Phase 3: Acquire `llm-provider-router` Repository (With Zero-Git ZIP Fallback)
1. If `pyproject.toml` exists in `<TARGET_DIR>`, run `git pull --ff-only` if `.git` + `git` are present.
2. Otherwise clone `https://github.com/productaivn-wq/llm-provider-router.git` into `<TARGET_DIR>`.
3. If `git` is missing or blocked: download `https://github.com/productaivn-wq/llm-provider-router/archive/refs/heads/main.zip`, extract into parent directory, and rename `llm-provider-router-main` -> `llm-provider-router`.

### Phase 4: ExecutionPolicy-Safe Isolated Install
- **NEVER** run `.venv\Scripts\Activate.ps1` (avoids PowerShell ExecutionPolicy blocks).
- Always use `<VENV_PY>`:
  - Windows: `<TARGET_DIR>\.venv\Scripts\python.exe`
  - macOS / Linux: `<TARGET_DIR>/.venv/bin/python`
1. Create `.venv`: `<PYTHON_EXE> -m venv "<TARGET_DIR>\.venv"`
2. Install package with `PYTHONUTF8=1`:
   `"<VENV_PY>" -m pip install --upgrade pip`
   `"<VENV_PY>" -m pip install -e "<TARGET_DIR>"`

### Phase 5: UTF-8/BOM-Safe Zero-Leak Key Configuration
Use Python `subprocess.run(..., input=api_key, encoding="utf-8", text=True)` so UTF-8/BOM/newline/shell-quoting bugs cannot happen and the key is saved to both `<TARGET_DIR>\.env` and `~/.llm_provider_router/.env` (works from any folder):

```python
import os, subprocess
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
api_key = """<YOUR_API_KEY>""".strip().lstrip("\ufeff")
proxy_url = """<PROXY_URL>""".strip().lstrip("\ufeff")
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
    env=env,
    input=api_key,
    encoding="utf-8",
    text=True,
    capture_output=True,
    check=False,
)
```
Assert `res.returncode == 0` and `"ok": true` in JSON.

### Phase 6: End-to-End Verification & Self-Healing
1. `<VENV_PY> -m llm_provider_router probe --json` -> `ok: true`
2. `<VENV_PY> -m llm_provider_router models --json` -> `count >= 1`
3. `<VENV_PY> -m llm_provider_router chat "Tra loi dung 2 chu: KET NOI OK" --json` -> `ok: true`
4. Self-heal cleanly if needed:
   - HTTP 403 -> verify `--user-agent LLM-Provider-Router/1.0` and re-probe.
   - HTTP 401 or non-ASCII error -> strip invisible BOM/spaces/newlines from key and rerun Phase 5.
   - Cooldown blocked -> run `reset-cooldowns` and retry.

### Phase 7: Auto-Connect Tools, Start Background Gateway + Web Chat UI & Present Visual Next Steps
1. Run one command to start the detached background gateway, create `Mo_Chat_AI.bat` + `Mo_Cong_AI.bat` (or `.command`), and auto-wire local tools (`OPENAI_BASE_URL`, `~/.codex/config.toml`, `~/.continue/config.json`):
   `"<VENV_PY>" -m llm_provider_router connect --start-gateway --install-dir "<TARGET_DIR>" --json`
2. Live-verify BOTH local endpoints return HTTP `200`:
   - `GET http://127.0.0.1:18766/` (Built-in Vietnamese Web Chat UI & Connection Hub)
   - `GET http://127.0.0.1:18766/v1/models`
3. Open `http://127.0.0.1:18766/` in the user's browser if supported in this desktop session (or tell them the exact clickable path to `Mo_Chat_AI.bat` / `Mo_Chat_AI.command`).
4. Finish with a clear visual Vietnamese summary covering ALL 3 questions ("Để làm gì?", "Đã kết nối những gì?", "Bước tiếp theo?"):
   - **Cài xong để làm gì:** Dùng tập trung `<models_count>` mô hình AI của công ty, tự chuyển dự phòng khi quá tải.
   - **Dùng ngay bây giờ:** Mở trình duyệt vào `http://127.0.0.1:18766/` hoặc nhấp đúp `<TARGET_DIR>\Mo_Chat_AI.bat` (Windows) / `<TARGET_DIR>/Mo_Chat_AI.command` (macOS).
   - **App AI đang dùng (Cursor / Antigravity / Cline / ChatBox):** Nếu muốn app này cũng gọi qua router công ty (vì app GUI đóng không cho sửa ngầm cấu hình đăng nhập), vào *Settings → OpenAI-Compatible Provider* điền đúng 3 dòng:
     - Base URL: `http://127.0.0.1:18766/v1`
     - API Key: `local-router`
     - Model: `router/auto`
```
