"""Self-contained zero-dependency Web Chat UI and Connection Hub for `LocalOpenAIGateway`."""

from __future__ import annotations

import html
import json


def render_chat_ui_html(
    *,
    gateway_url: str = "http://127.0.0.1:18766/v1",
    auth_required: bool = False,
) -> str:
    """Render a clean Vietnamese UTF-8 Web Chat UI and AI Connection Hub."""
    safe_url = html.escape(gateway_url, quote=True)
    js_url = json.dumps(gateway_url)
    js_auth = "true" if auth_required else "false"
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Trợ Lý AI Nội Bộ — LLM Provider Router</title>
  <style>
    :root {{
      --bg: #f4f6fb;
      --card: #ffffff;
      --ink: #0f172a;
      --muted: #475569;
      --border: #e2e8f0;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --ok-bg: #dcfce7;
      --ok-ink: #166534;
      --warn-bg: #fef3c7;
      --warn-ink: #92400e;
      --user-bg: #dbeafe;
      --ai-bg: #f8fafc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }}
    .wrap {{
      max-width: 980px;
      margin: 0 auto;
      padding: 20px 16px 36px;
    }}
    .header {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px 20px;
      box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    }}
    .title h1 {{
      margin: 0;
      font-size: 20px;
    }}
    .title p {{
      margin: 4px 0 0;
      font-size: 13px;
      color: var(--muted);
    }}
    .badge {{
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
      background: var(--warn-bg);
      color: var(--warn-ink);
    }}
    .badge.ok {{
      background: var(--ok-bg);
      color: var(--ok-ink);
    }}
    .tabs {{
      display: flex;
      gap: 8px;
      margin: 16px 0 12px;
    }}
    .tab-btn {{
      border: 1px solid var(--border);
      background: var(--card);
      color: var(--muted);
      border-radius: 10px;
      padding: 9px 16px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }}
    .tab-btn.active {{
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }}
    .panel {{
      display: none;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    }}
    .panel.active {{ display: block; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }}
    .toolbar label {{
      font-size: 13px;
      font-weight: 600;
      color: var(--muted);
    }}
    select, input[type="password"], input[type="text"] {{
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 14px;
      background: #ffffff;
      color: var(--ink);
    }}
    .messages {{
      border: 1px solid var(--border);
      border-radius: 12px;
      min-height: 300px;
      max-height: 460px;
      overflow-y: auto;
      padding: 14px;
      background: #fcfdff;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .msg {{
      padding: 10px 14px;
      border-radius: 10px;
      max-width: 88%;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 14px;
    }}
    .msg.user {{
      align-self: flex-end;
      background: var(--user-bg);
    }}
    .msg.ai {{
      align-self: flex-start;
      background: var(--ai-bg);
      border: 1px solid var(--border);
    }}
    .msg-meta {{
      margin-top: 6px;
      font-size: 11px;
      color: var(--muted);
      display: flex;
      gap: 10px;
      align-items: center;
    }}
    .copy-mini {{
      border: 1px solid var(--border);
      background: #ffffff;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 11px;
      cursor: pointer;
    }}
    .composer {{
      display: flex;
      gap: 10px;
      margin-top: 12px;
    }}
    textarea {{
      flex: 1;
      resize: vertical;
      min-height: 54px;
      max-height: 160px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
      font-family: inherit;
      font-size: 14px;
    }}
    .primary {{
      background: var(--accent);
      color: #ffffff;
      border: none;
      border-radius: 10px;
      padding: 0 20px;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
    }}
    .primary:hover {{ background: var(--accent-hover); }}
    .primary:disabled {{ opacity: 0.55; cursor: wait; }}
    .kv-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      margin: 12px 0 18px;
    }}
    .kv-card {{
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      background: #f8fafc;
    }}
    .kv-label {{
      font-size: 12px;
      color: var(--muted);
      font-weight: 600;
    }}
    .kv-val {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-top: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      word-break: break-all;
    }}
    .guide-list {{
      margin: 8px 0 0;
      padding-left: 18px;
      font-size: 14px;
    }}
    .guide-list li {{ margin-bottom: 6px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <div class="title">
        <h1>Trợ Lý AI Nội Bộ — LLM Provider Router</h1>
        <p>Cổng kết nối AI tập trung trên máy cá nhân · Tự động chuyển đổi mô hình khi quá tải</p>
      </div>
      <div id="status-badge" class="badge">Đang kiểm tra kết nối...</div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" data-tab="chat" onclick="switchTab('chat')">1. Chat AI Ngay</button>
      <button class="tab-btn" data-tab="connect" onclick="switchTab('connect')">2. Kết nối Trợ lý AI</button>
    </div>

    <section id="panel-chat" class="panel active">
      <div class="toolbar">
        <label for="model-select">Mô hình:</label>
        <select id="model-select">
          <option value="router/auto">router/auto (Tự động chọn tốt nhất)</option>
          <option value="router/coding">router/coding (Chuyên lập trình)</option>
          <option value="router/fast">router/fast (Phản hồi nhanh)</option>
        </select>
        <span id="token-wrap" style="display:none;">
          <label for="gw-token">Mã cổng nội bộ:</label>
          <input id="gw-token" type="password" placeholder="Nhập ROUTER_GATEWAY_TOKEN" />
        </span>
      </div>
      <div id="messages" class="messages">
        <div class="msg ai">Xin chào! Cổng AI nội bộ đã sẵn sàng. Hãy nhập câu hỏi hoặc yêu cầu công việc bên dưới để bắt đầu ngay.</div>
      </div>
      <div class="composer">
        <textarea id="prompt-input" placeholder="Nhập câu hỏi tại đây (Nhấn Ctrl+Enter để gửi)..."></textarea>
        <button id="send-btn" class="primary" onclick="sendChat()">Gửi</button>
      </div>
    </section>

    <section id="panel-connect" class="panel">
      <h3>Công cụ này để làm gì?</h3>
      <p>Bộ định tuyến giúp bạn dùng chung hạn mức AI nội bộ của công ty qua <strong>1 đầu mối duy nhất</strong> trên máy cá nhân, không cần tự gắn thẻ thanh toán và tự động chuyển mô hình dự phòng nếu một máy chủ bận.</p>

      <h3>3 thông tin dùng để gắn vào bất kỳ ứng dụng AI nào</h3>
      <div class="kv-grid">
        <div class="kv-card">
          <div class="kv-label">Địa chỉ kết nối (Base URL)</div>
          <div class="kv-val">
            <span id="val-url">{safe_url}</span>
            <button class="copy-mini" onclick="copyText('val-url', this)">Sao chép</button>
          </div>
        </div>
        <div class="kv-card">
          <div class="kv-label">Mã kết nối nội bộ (API Key)</div>
          <div class="kv-val">
            <span id="val-key">local-router</span>
            <button class="copy-mini" onclick="copyText('val-key', this)">Sao chép</button>
          </div>
        </div>
        <div class="kv-card">
          <div class="kv-label">Tên mô hình mặc định (Model)</div>
          <div class="kv-val">
            <span id="val-model">router/auto</span>
            <button class="copy-mini" onclick="copyText('val-model', this)">Sao chép</button>
          </div>
        </div>
      </div>

      <h3>Hướng dẫn gắn nhanh cho từng công cụ</h3>
      <ul class="guide-list">
        <li><strong>Người dùng văn phòng (Non-Tech):</strong> Không cần cấu hình thêm gì — dùng ngay tab <em>Chat AI Ngay</em> ở trang này (mở lại bất cứ lúc nào bằng file <code>Mo_Chat_AI.bat</code> hoặc <code>Mo_Chat_AI.command</code>).</li>
        <li><strong>Codex / Continue / Terminal AI:</strong> Lệnh <code>llm-router connect --start-gateway</code> đã tự động thêm cấu hình vào máy khi phát hiện sẵn công cụ.</li>
        <li><strong>Cursor / Antigravity / Cline / ChatBox:</strong> Mở <em>Settings → Models / API Provider</em> → chọn <em>OpenAI Compatible</em> → dán 3 giá trị ở trên và nhấn Save.</li>
      </ul>
    </section>
  </div>

  <script>
    const GATEWAY_URL = {js_url};
    const AUTH_REQUIRED = {js_auth};
    const historyList = [];

    if (AUTH_REQUIRED) {{
      document.getElementById("token-wrap").style.display = "inline-flex";
    }}

    function switchTab(name) {{
      document.querySelectorAll(".tab-btn").forEach((b) => {{
        b.classList.toggle("active", b.dataset.tab === name);
      }});
      document.querySelectorAll(".panel").forEach((p) => {{
        p.classList.toggle("active", p.id === "panel-" + name);
      }});
    }}

    function copyText(spanId, btn) {{
      const txt = document.getElementById(spanId).textContent;
      navigator.clipboard.writeText(txt).then(() => {{
        const orig = btn.textContent;
        btn.textContent = "Đã chép";
        setTimeout(() => (btn.textContent = orig), 1400);
      }});
    }}

    function authHeaders() {{
      const hdrs = {{ "Content-Type": "application/json" }};
      const tok = (document.getElementById("gw-token").value || "").trim() || "local-router";
      hdrs["Authorization"] = "Bearer " + tok;
      return hdrs;
    }}

    async function refreshStatus() {{
      const badge = document.getElementById("status-badge");
      try {{
        const hzResp = await fetch("/healthz");
        const hz = await hzResp.json();
        const mResp = await fetch("/v1/models", {{ headers: authHeaders() }});
        let countText = "";
        if (mResp.ok) {{
          const mData = await mResp.json();
          const list = Array.isArray(mData.data) ? mData.data : [];
          const sel = document.getElementById("model-select");
          const existing = new Set(Array.from(sel.options).map((o) => o.value));
          list.forEach((m) => {{
            if (m && m.id && !existing.has(m.id)) {{
              const opt = document.createElement("option");
              opt.value = m.id;
              opt.textContent = m.id;
              sel.appendChild(opt);
              existing.add(m.id);
            }}
          }});
          const upstreamCount = Math.max(0, list.length - 3);
          countText = " — " + upstreamCount + " mô hình AI sẵn sàng";
        }}
        if (hz.ok) {{
          badge.classList.add("ok");
          badge.textContent = "Đã kết nối" + countText;
        }} else {{
          badge.classList.remove("ok");
          badge.textContent = "Chưa cấu hình khóa kết nối";
        }}
      }} catch (_err) {{
        badge.classList.remove("ok");
        badge.textContent = "Không kết nối được cổng cục bộ";
      }}
    }}

    function appendMessage(role, text, metaText) {{
      const box = document.getElementById("messages");
      const wrap = document.createElement("div");
      wrap.className = "msg " + role;
      wrap.textContent = text;
      if (metaText) {{
        const meta = document.createElement("div");
        meta.className = "msg-meta";
        const span = document.createElement("span");
        span.textContent = metaText;
        meta.appendChild(span);
        const btn = document.createElement("button");
        btn.className = "copy-mini";
        btn.textContent = "Sao chép";
        btn.onclick = () => navigator.clipboard.writeText(text);
        meta.appendChild(btn);
        wrap.appendChild(meta);
      }}
      box.appendChild(wrap);
      box.scrollTop = box.scrollHeight;
    }}

    async function sendChat() {{
      const input = document.getElementById("prompt-input");
      const btn = document.getElementById("send-btn");
      const prompt = input.value.trim();
      if (!prompt) return;
      const model = document.getElementById("model-select").value;
      input.value = "";
      appendMessage("user", prompt);
      historyList.push({{ role: "user", content: prompt }});
      btn.disabled = true;
      btn.textContent = "Đang trả lời...";
      try {{
        const resp = await fetch("/v1/chat/completions", {{
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({{ model: model, messages: historyList.slice(-12) }}),
        }});
        const data = await resp.json();
        if (!resp.ok) {{
          const errMsg = (data && data.error && data.error.message) || ("HTTP " + resp.status);
          appendMessage("ai", "Lỗi kết nối: " + errMsg);
        }} else {{
          const reply = (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || "";
          historyList.push({{ role: "assistant", content: reply }});
          const xr = data.x_router || {{}};
          const meta = (xr.resolved_model || model) + (xr.latency_ms ? " · " + Math.round(xr.latency_ms) + " ms" : "");
          appendMessage("ai", reply, meta);
        }}
      }} catch (err) {{
        appendMessage("ai", "Không thể gọi cổng cục bộ: " + err);
      }} finally {{
        btn.disabled = false;
        btn.textContent = "Gửi";
      }}
    }}

    document.getElementById("prompt-input").addEventListener("keydown", (ev) => {{
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {{
        ev.preventDefault();
        sendChat();
      }}
    }});

    refreshStatus();
  </script>
</body>
</html>
"""
