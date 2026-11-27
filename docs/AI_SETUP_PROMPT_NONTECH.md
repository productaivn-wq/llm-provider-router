# Hướng Dẫn Cài Đặt 1-Shot Cho Người Không Chuyên Kỹ Thuật (Non-Tech)

Tài liệu này giúp nhân sự không chuyên kỹ thuật (Kinh doanh, Sản phẩm, Nhân sự, Kế toán, Truyền thông, Trợ lý, Ban Giám Đốc) cài xong **`llm-provider-router`** chỉ bằng **1 lần dán**, để **Trợ lý AI hiện tại** (Antigravity, Claude, Codex, Cursor) tự giữ vai trò điều phối chính và **tự động giao việc nặng cho Sub-Agent OpenAI công ty**.

Xem giải thích trực quan ("Cài để làm gì & Làm gì tiếp theo?"): [docs/VISUAL_GUIDE_VI.md](VISUAL_GUIDE_VI.md)

---

## Phần 1: Prompt Ngắn (1-Shot Online)

Sao chép nguyên văn khung bên dưới, thay `<PROXY_URL>` và `<YOUR_API_KEY>` bằng thông tin được cấp riêng, rồi dán **một lần duy nhất** vào trợ lý AI trên máy tính của bạn:

```text
Bạn là trợ lý kỹ thuật toàn quyền trên máy tính này. Tôi KHÔNG rành lập trình (non-tech).
Hãy tự động đọc hướng dẫn chuẩn tại:
https://raw.githubusercontent.com/productaivn-wq/llm-provider-router/main/docs/AI_SETUP_PROMPT_NONTECH.md
và thực hiện ĐẦY ĐỦ từ Phase 1 đến Phase 7 trong 1 lượt duy nhất để cài xong `llm-provider-router`, tự gắn quy tắc để trợ lý AI của tôi tự giao việc cho OpenAI Sub-Agent sau khi cài xong, và chạy thử `delegate` thật thành công.

Thông tin kết nối của tôi:
- Địa chỉ máy chủ: <PROXY_URL>
- Mã khóa riêng: <YOUR_API_KEY>

Quy tắc bắt buộc:
- KHÔNG hỏi tôi gõ lệnh hay tự sửa lỗi kỹ thuật; tự xử lý mọi lỗi UTF-8/BOM, Python, hoặc git.
- KHÔNG in hoặc làm lộ mã khóa riêng ra màn hình.
- Sau khi chạy xong `connect` và thử `delegate`, hãy trả lời thật trực quan bằng tiếng Việt đơn giản: công cụ này dùng để làm gì, đã tự gắn vào trợ lý AI nào, và tôi chỉ cần làm gì tiếp theo.
```

---

## Phần 2: Runbook Tự Hành Đầy Đủ 7 Phase (Dành Cho Trợ Lý AI — Hoạt Động Cả Khi Offline / Không Đọc Web)

```text
[1-SHOT AUTONOMOUS SETUP & ORCHESTRATOR AUTO-WIRE RUNBOOK — NON-TECH USER]
Proxy URL: <PROXY_URL>
Personal Key: <YOUR_API_KEY>

### GOLDEN RULE (BẮT BUỘC TUÂN THỦ)
The user is NON-TECHNICAL.
- NEVER ask the user to open a terminal, run shell commands, edit files, adjust PowerShell ExecutionPolicy, or troubleshoot UTF-8/Python/Git/pip errors.
- Execute every phase autonomously in ONE pass.
- NEVER echo, log, or print `<YOUR_API_KEY>` in command output or user-facing messages.
- Do NOT tell the user to open a separate browser chat page or install a new app; wire their CURRENT AI assistant (Antigravity / Claude Code / Codex / Cursor) as Orchestrator + OpenAI Sub-Agent.
- Reply at the end in warm, plain, visual Vietnamese explaining: WHY it was installed, WHICH assistant was auto-wired, and WHAT exact 1-step action they do next (open a new chat & work normally).

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
1. Probe Python candidates (`py -3`, `python3`, `python`, `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`, `/opt/homebrew/bin/python3`).
2. Verify `sys.version_info >= (3, 10)` and reject Windows Store `WindowsApps` stubs.
3. If no valid Python 3.10+ exists, install silently (`winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent` on Windows, `brew install python@3.12` on macOS, or `apt`/`dnf` on Linux) and refresh lookup.

### Phase 3: Acquire `llm-provider-router` Repository (With Zero-Git ZIP Fallback)
1. If `pyproject.toml` exists in `<TARGET_DIR>`, run `git pull --ff-only` if `.git` + `git` exist.
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

### Phase 6: Auto-Wire Orchestrator -> OpenAI Sub-Agent Delegation
Run `connect` so the user's current AI assistant(s) automatically receive permanent Orchestrator + OpenAI Sub-Agent rules & skills (Antigravity, Claude Code, Codex, Cursor, plus `LLM_ROUTER_*` env vars):
`"<VENV_PY>" -m llm_provider_router connect --install-dir "<TARGET_DIR>" --python-exe "<VENV_PY>" --json`
(Also pass `--workspace "<CURRENT_WORKSPACE_DIR>"` if running inside a Cursor or Antigravity project workspace.)
Inspect `auto_connected` in the JSON output to see the exact rules/skills written.

### Phase 7: End-to-End Sub-Agent Proof, Self-Healing & Plain Vietnamese Visual Summary
1. Verify live proxy + sub-agent delegation end-to-end:
   - `"<VENV_PY>" -m llm_provider_router models --json` -> check `count >= 1`
   - `"<VENV_PY>" -m llm_provider_router delegate --role writing "Tra loi dung 1 cau tieng Viet: Sub-Agent OpenAI da san sang." --json` -> assert `"ok": true`
2. Self-heal cleanly if needed:
   - HTTP 403 -> verify `--user-agent LLM-Provider-Router/1.0` and re-probe.
   - HTTP 401 or non-ASCII error -> strip invisible BOM/spaces/newlines from key and rerun Phase 5.
3. Reply to the user in **warm, plain, visual Vietnamese** answering ALL 3 questions (ZERO dev jargon, ZERO raw API key):
   - **Công cụ này để làm gì:** Giữ nguyên trợ lý AI quen dùng (Antigravity / Claude / Codex / Cursor) làm "nhạc trưởng" hiểu ý bạn, còn các việc nặng (soạn thảo, tóm tắt, phân tích, xử lý dữ liệu) sẽ tự giao sang `<models_count>` mô hình OpenAI của công ty.
   - **Máy đã tự kích hoạt gì:** Liệt kê gọn các trợ lý AI vừa được tự động gắn quy tắc từ `connect --json` (và tên model OpenAI vừa trả lời thử thành công).
   - **Bạn cần làm gì tiếp theo:**
     1. Mở **một cuộc trò chuyện MỚI** trong chính trợ lý AI đang dùng (để trợ lý nạp quy tắc mới, không cần mở app hay trang web nào khác).
     2. Nếu muốn kiểm chứng ngay, dán câu: *"Hãy giao một việc nhỏ cho trợ lý phụ OpenAI qua llm-router để kiểm tra kết nối và báo lại tên mô hình vừa trả lời."*
     3. Sau đó cứ giao việc bình thường mỗi ngày.
```
