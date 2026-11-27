"""Auto-connect local AI tools, detached background gateway, and 1-click launchers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from .config import RouterConfig, default_global_env_path

_CODEX_BLOCK_RE = re.compile(
    r"\n?# BEGIN LLM-PROVIDER-ROUTER[\s\S]*?# END LLM-PROVIDER-ROUTER\n?",
    re.MULTILINE,
)
_SHELL_BLOCK_RE = re.compile(
    r"\n?# >>> llm-provider-router >>>[\s\S]*?# <<< llm-provider-router <<<\n?",
    re.MULTILINE,
)


def is_gateway_healthy(
    host: str = "127.0.0.1", port: int = 18766, *, timeout: float = 2.0
) -> tuple[bool, dict[str, Any]]:
    """Check whether the local OpenAI-compatible gateway is already listening and healthy."""
    url = f"http://{host}:{int(port)}/healthz"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=max(0.5, timeout)) as resp:
            if resp.status != 200:
                return False, {}
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if isinstance(data, dict) and "status" in data:
                return True, data
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return False, {}
    return False, {}


def _pid_file_path() -> Path:
    return default_global_env_path().parent / "gateway.pid"


def ensure_gateway_running(
    *,
    host: str = "127.0.0.1",
    port: int = 18766,
    env_file: Path | None = None,
    python_exe: str | None = None,
    wait_sec: float = 6.0,
) -> dict[str, Any]:
    """Start `llm-router serve` detached in the background if not already healthy."""
    healthy, payload = is_gateway_healthy(host, port)
    if healthy:
        return {
            "running": True,
            "already_running": True,
            "host": host,
            "port": int(port),
            "health": payload,
        }

    py_bin = python_exe or sys.executable
    cmd = [
        py_bin,
        "-m",
        "llm_provider_router",
        "serve",
        "--host",
        host,
        "--port",
        str(int(port)),
    ]
    if env_file is not None and Path(env_file).is_file():
        cmd.extend(["--env-file", str(env_file)])

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        popen_kwargs["creationflags"] = detached | new_group | no_win
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    pid_path = _pid_file_path()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(proc.pid), encoding="utf-8")

    deadline = time.monotonic() + max(1.0, wait_sec)
    while time.monotonic() < deadline:
        ok, health = is_gateway_healthy(host, port, timeout=1.0)
        if ok:
            return {
                "running": True,
                "already_running": False,
                "pid": proc.pid,
                "host": host,
                "port": int(port),
                "health": health,
            }
        time.sleep(0.25)

    return {
        "running": False,
        "already_running": False,
        "pid": proc.pid,
        "host": host,
        "port": int(port),
        "error": f"Gateway did not respond on http://{host}:{port}/healthz within {wait_sec:.1f}s",
    }


def write_launchers(
    target_dir: Path,
    *,
    venv_py: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 18766,
) -> dict[str, str]:
    """Generate UTF-8-safe 1-click daily launchers for Web Chat UI and local gateway."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    win_py = str(venv_py) if venv_py else r'.venv\Scripts\python.exe'
    posix_py = str(venv_py) if venv_py else "./.venv/bin/python"
    chat_url = f"http://{host}:{int(port)}/"

    bat_chat = target_dir / "Mo_Chat_AI.bat"
    bat_chat.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "set PYTHONUTF8=1\r\n"
        "set PYTHONIOENCODING=utf-8\r\n"
        f"title Tro Ly AI Noi Bo ({chat_url})\r\n"
        'cd /d "%~dp0"\r\n'
        f'"{win_py}" -m llm_provider_router connect --start-gateway --open-ui --json >nul 2>&1\r\n'
        "if errorlevel 1 (\r\n"
        f'  start "" "{chat_url}"\r\n'
        f'  "{win_py}" -m llm_provider_router serve --host {host} --port {int(port)}\r\n'
        ")\r\n",
        encoding="utf-8",
    )

    bat_serve = target_dir / "Mo_Cong_AI.bat"
    bat_serve.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "set PYTHONUTF8=1\r\n"
        "set PYTHONIOENCODING=utf-8\r\n"
        f"title Cong AI Noi Bo ({chat_url}v1)\r\n"
        'cd /d "%~dp0"\r\n'
        f"echo Dang khoi dong Cong AI cuc bo tai {chat_url}v1 ...\r\n"
        f'"{win_py}" -m llm_provider_router serve --host {host} --port {int(port)}\r\n'
        "pause\r\n",
        encoding="utf-8",
    )

    cmd_chat = target_dir / "Mo_Chat_AI.command"
    cmd_chat.write_text(
        "#!/usr/bin/env bash\n"
        "export PYTHONUTF8=1\n"
        "export PYTHONIOENCODING=utf-8\n"
        'cd "$(dirname "$0")"\n'
        f'if ! "{posix_py}" -m llm_provider_router connect --start-gateway --open-ui --json >/dev/null 2>&1; then\n'
        f'  (sleep 1 && (open "{chat_url}" 2>/dev/null || xdg-open "{chat_url}" 2>/dev/null || true)) &\n'
        f'  exec "{posix_py}" -m llm_provider_router serve --host {host} --port {int(port)}\n'
        "fi\n",
        encoding="utf-8",
    )

    cmd_serve = target_dir / "Mo_Cong_AI.command"
    cmd_serve.write_text(
        "#!/usr/bin/env bash\n"
        "export PYTHONUTF8=1\n"
        "export PYTHONIOENCODING=utf-8\n"
        'cd "$(dirname "$0")"\n'
        f'echo "Dang khoi dong Cong AI cuc bo tai {chat_url}v1 ..."\n'
        f'exec "{posix_py}" -m llm_provider_router serve --host {host} --port {int(port)}\n',
        encoding="utf-8",
    )

    for p in (cmd_chat, cmd_serve):
        try:
            os.chmod(p, 0o755)
        except OSError:
            pass

    return {
        "chat_launcher_win": str(bat_chat),
        "gateway_launcher_win": str(bat_serve),
        "chat_launcher_posix": str(cmd_chat),
        "gateway_launcher_posix": str(cmd_serve),
    }


def _backup_file(path: Path) -> None:
    if path.is_file():
        bak = path.with_name(path.name + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)


def wire_codex_config(
    home_dir: Path, gateway_url: str, *, dry_run: bool = False
) -> dict[str, Any]:
    """Safely add an optional `[model_providers.llm_router]` profile to `~/.codex/config.toml`."""
    codex_dir = Path(home_dir) / ".codex"
    if not codex_dir.is_dir():
        return {"client": "codex", "status": "not_installed"}

    cfg_path = codex_dir / "config.toml"
    existing = cfg_path.read_text(encoding="utf-8", errors="replace") if cfg_path.is_file() else ""
    if "model_providers.llm_router" in existing and "# BEGIN LLM-PROVIDER-ROUTER" not in existing:
        return {"client": "codex", "status": "already_configured", "path": str(cfg_path)}

    block = (
        "\n# BEGIN LLM-PROVIDER-ROUTER\n"
        "[model_providers.llm_router]\n"
        'name = "LLM Provider Router"\n'
        f'base_url = "{gateway_url}"\n'
        'env_key = "OPENAI_API_KEY"\n'
        'wire_api = "chat"\n'
        "# END LLM-PROVIDER-ROUTER\n"
    )
    cleaned = _CODEX_BLOCK_RE.sub("", existing).rstrip()
    updated = (cleaned + "\n" + block) if cleaned else block.lstrip("\n")
    if not dry_run:
        _backup_file(cfg_path)
        cfg_path.write_text(updated, encoding="utf-8")
    return {"client": "codex", "status": "configured", "path": str(cfg_path), "dry_run": dry_run}


def wire_continue_config(
    home_dir: Path, gateway_url: str, *, dry_run: bool = False
) -> dict[str, Any]:
    """Safely upsert `LLM Provider Router (Auto)` inside `~/.continue/config.json`."""
    cfg_path = Path(home_dir) / ".continue" / "config.json"
    if not cfg_path.is_file():
        return {"client": "continue", "status": "not_installed"}

    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, json.JSONDecodeError) as exc:
        return {"client": "continue", "status": "skipped_invalid_json", "error": str(exc)}
    if not isinstance(data, dict):
        return {"client": "continue", "status": "skipped_invalid_schema"}

    models = data.get("models")
    if not isinstance(models, list):
        models = []
        data["models"] = models

    entry = {
        "title": "LLM Provider Router (Auto)",
        "provider": "openai",
        "model": "router/auto",
        "apiBase": gateway_url,
        "apiKey": "local-router",
    }
    replaced = False
    for idx, item in enumerate(models):
        if isinstance(item, dict) and item.get("title") == entry["title"]:
            models[idx] = entry
            replaced = True
            break
    if not replaced:
        models.append(entry)

    if not dry_run:
        _backup_file(cfg_path)
        cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"client": "continue", "status": "configured", "path": str(cfg_path), "dry_run": dry_run}


def wire_shell_env(
    home_dir: Path,
    gateway_url: str,
    *,
    install_dir: Path,
    dry_run: bool = False,
    posix_only_for_test: bool = False,
) -> dict[str, Any]:
    """Persist gateway helper env vars cleanly without overwriting unrelated user API keys."""
    if os.name == "nt" and not posix_only_for_test:
        if dry_run:
            return {"client": "windows_user_env", "status": "dry_run", "gateway_url": gateway_url}
        try:
            import winreg

            set_keys: list[str] = []
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
            ) as reg:
                winreg.SetValueEx(reg, "LLM_ROUTER_HOME", 0, winreg.REG_SZ, str(install_dir))
                winreg.SetValueEx(reg, "LLM_ROUTER_GATEWAY_URL", 0, winreg.REG_SZ, gateway_url)
                set_keys.extend(["LLM_ROUTER_HOME", "LLM_ROUTER_GATEWAY_URL"])
                try:
                    cur_base, _ = winreg.QueryValueEx(reg, "OPENAI_BASE_URL")
                except FileNotFoundError:
                    cur_base = ""
                if not str(cur_base).strip() or "127.0.0.1:18766" in str(cur_base):
                    winreg.SetValueEx(reg, "OPENAI_BASE_URL", 0, winreg.REG_SZ, gateway_url)
                    set_keys.append("OPENAI_BASE_URL")
                    try:
                        cur_key, _ = winreg.QueryValueEx(reg, "OPENAI_API_KEY")
                    except FileNotFoundError:
                        cur_key = ""
                    if not str(cur_key).strip():
                        winreg.SetValueEx(reg, "OPENAI_API_KEY", 0, winreg.REG_SZ, "local-router")
                        set_keys.append("OPENAI_API_KEY")
            return {"client": "windows_user_env", "status": "configured", "vars": set_keys}
        except OSError as exc:
            return {"client": "windows_user_env", "status": "error", "error": str(exc)}

    home = Path(home_dir)
    rc_targets = [home / ".bashrc", home / ".zshrc"]
    block = (
        "\n# >>> llm-provider-router >>>\n"
        f'export LLM_ROUTER_HOME="{install_dir}"\n'
        f'export LLM_ROUTER_GATEWAY_URL="{gateway_url}"\n'
        f'export OPENAI_BASE_URL="${{OPENAI_BASE_URL:-{gateway_url}}}"\n'
        'export OPENAI_API_KEY="${OPENAI_API_KEY:-local-router}"\n'
        "# <<< llm-provider-router <<<\n"
    )
    updated_files: list[str] = []
    for rc in rc_targets:
        if rc.is_file() or rc.name == ".bashrc":
            existing = rc.read_text(encoding="utf-8", errors="replace") if rc.is_file() else ""
            cleaned = _SHELL_BLOCK_RE.sub("", existing).rstrip()
            new_txt = (cleaned + "\n" + block) if cleaned else block.lstrip("\n")
            if not dry_run:
                _backup_file(rc)
                rc.write_text(new_txt, encoding="utf-8")
            updated_files.append(str(rc))
    return {"client": "posix_shell_env", "status": "configured", "files": updated_files, "dry_run": dry_run}


def connect_clients(
    *,
    env_file: Path | None = None,
    install_dir: Path | None = None,
    home_dir: Path | None = None,
    start_gateway: bool = True,
    clients: str = "auto",
    open_ui: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ensure background gateway is active, generate 1-click launchers, and auto-wire local tools."""
    cfg = RouterConfig.from_env(env_file=env_file)
    host = cfg.gateway_host
    port = cfg.gateway_port
    gateway_url = f"http://{host}:{port}/v1"
    chat_ui_url = f"http://{host}:{port}/"

    resolved_home = Path(home_dir) if home_dir is not None else Path.home()
    resolved_install = Path(install_dir) if install_dir is not None else Path.cwd()
    eff_env = env_file
    if eff_env is None:
        cand = resolved_install / ".env"
        if cand.is_file():
            eff_env = cand
        elif default_global_env_path().is_file():
            eff_env = default_global_env_path()

    gateway_status: dict[str, Any] = {"running": False, "skipped": True}
    if start_gateway and not dry_run:
        gateway_status = ensure_gateway_running(host=host, port=port, env_file=eff_env)

    launchers = (
        write_launchers(resolved_install, host=host, port=port)
        if not dry_run
        else {"dry_run": "true"}
    )

    requested = {item.strip().lower() for item in clients.split(",") if item.strip()}
    run_all = "auto" in requested or "all" in requested

    auto_connected: list[dict[str, Any]] = []
    if run_all or "shell" in requested or "env" in requested:
        auto_connected.append(
            wire_shell_env(resolved_home, gateway_url, install_dir=resolved_install, dry_run=dry_run)
        )
    if run_all or "codex" in requested:
        auto_connected.append(wire_codex_config(resolved_home, gateway_url, dry_run=dry_run))
    if run_all or "continue" in requested:
        auto_connected.append(wire_continue_config(resolved_home, gateway_url, dry_run=dry_run))

    if open_ui and not dry_run:
        try:
            webbrowser.open(chat_ui_url)
        except OSError:
            pass

    return {
        "ok": True,
        "gateway_url": gateway_url,
        "chat_ui_url": chat_ui_url,
        "default_gateway_api_key": "local-router",
        "default_model": "router/auto",
        "coding_model": "router/coding",
        "gateway": gateway_status,
        "launchers": launchers,
        "auto_connected": auto_connected,
        "manual_gui_clients": [
            {
                "name": "Web Chat AI (Built-in Browser UI)",
                "how": f"Mở trực tiếp {chat_ui_url} hoặc nhấp đúp Mo_Chat_AI.bat / Mo_Chat_AI.command",
            },
            {
                "name": "Cursor / Antigravity / Cline / ChatBox",
                "base_url": gateway_url,
                "api_key": "local-router",
                "model": "router/auto",
                "how": "Settings → OpenAI-Compatible Provider → nhập 3 giá trị trên và Save.",
            },
        ],
    }
