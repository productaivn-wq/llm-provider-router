"""Auto-wire Orchestrator AI tools (AGY, Claude Code, Codex, Cursor) to offload sub-agents to OpenAI."""

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
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_CODING_MODEL,
    VERIFIED_MODELS,
    RouterConfig,
    default_global_env_path,
)

_CODEX_TOML_BLOCK_RE = re.compile(
    r"\n?# BEGIN LLM-PROVIDER-ROUTER[\s\S]*?# END LLM-PROVIDER-ROUTER\n?",
    re.MULTILINE,
)
_ORCHESTRATOR_BLOCK_RE = re.compile(
    r"\n?(?:#|<!--) BEGIN LLM-PROVIDER-ROUTER-ORCHESTRATOR[\s\S]*?END LLM-PROVIDER-ROUTER-ORCHESTRATOR(?: -->)?\n?",
    re.MULTILINE,
)
_SHELL_BLOCK_RE = re.compile(
    r"\n?# >>> llm-provider-router >>>[\s\S]*?# <<< llm-provider-router <<<\n?",
    re.MULTILINE,
)
_CANARY_MARKER = "CANARY:"


def _has_canary_guard(text: str) -> bool:
    return _CANARY_MARKER in text


def _backup_file(path: Path) -> None:
    if path.is_file():
        bak = path.with_name(path.name + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)


def _resolve_python_exe(install_dir: Path, python_exe: str | None = None) -> str:
    if python_exe:
        return str(python_exe)
    win_venv = install_dir / ".venv" / "Scripts" / "python.exe"
    if win_venv.is_file():
        return str(win_venv)
    posix_venv = install_dir / ".venv" / "bin" / "python"
    if posix_venv.is_file():
        return str(posix_venv)
    return sys.executable


def render_orchestrator_rule_body(python_exe: str, install_dir: Path) -> str:
    """Return concise Orchestrator -> OpenAI Sub-Agent delegation rules (no secrets)."""
    py_cmd = f'"{python_exe}" -m llm_provider_router'
    return (
        "# OpenAI Sub-Agent Offloading (`llm-provider-router`)\n\n"
        "You remain the **primary Orchestrator** (reasoning, planning, file edits, tool calls, and replying to the user).\n"
        "Offload heavy sub-agent worker tasks to company OpenAI models through `llm-provider-router`:\n\n"
        "- **Single sub-agent task** (`general`, `writing`, `analysis`, `coding`, `review`):\n"
        f'  `{py_cmd} delegate --role <role> "<task>" [--context-file <path>] --json`\n'
        "- **Parallel multi-task sub-agent batch**:\n"
        f'  `{py_cmd} batch --tasks-file <tasks.json> --json`\n'
        "- **Installed router directory**: `" + str(install_dir) + "`\n"
        f"- **Routing behavior**: `coding`/`review` route to `{DEFAULT_CODING_MODEL}`; "
        f"`general`/`writing`/`analysis` route to `{DEFAULT_CHAT_MODEL}`.\n"
        f"- **Verified working models (10)**: {', '.join(f'`{m}`' for m in VERIFIED_MODELS)}.\n"
        "- **Guardrails**: Never echo or commit `.env` API keys. Only perform the work yourself as fallback if `delegate` returns `ok: false`.\n"
    )


def render_antigravity_rule_file(python_exe: str, install_dir: Path) -> str:
    body = render_orchestrator_rule_body(python_exe, install_dir)
    return "---\ntrigger: always_on\n---\n\n" + body


def render_cursor_mdc_file(python_exe: str, install_dir: Path) -> str:
    body = render_orchestrator_rule_body(python_exe, install_dir)
    return (
        "---\n"
        "description: Delegate heavy sub-agent tasks to OpenAI via llm-provider-router while keeping Cursor as Orchestrator.\n"
        "alwaysApply: true\n"
        "---\n\n" + body
    )


def render_claude_subagent_file(python_exe: str, install_dir: Path) -> str:
    body = render_orchestrator_rule_body(python_exe, install_dir)
    return (
        "---\n"
        "name: openai-worker\n"
        "description: Use this sub-agent to execute drafting, analysis, translation, coding, or review subtasks on company OpenAI models via llm-provider-router.\n"
        "tools: Bash, Read\n"
        "---\n\n" + body
    )


def render_skill_file(python_exe: str, install_dir: Path) -> str:
    body = render_orchestrator_rule_body(python_exe, install_dir)
    return (
        "---\n"
        "name: llm-router-subagent\n"
        "description: Delegate sub-agent tasks or parallel worker batches to OpenAI via `llm-provider-router` while keeping the main AI as Orchestrator.\n"
        "---\n\n" + body
    )


def is_gateway_healthy(
    host: str = "127.0.0.1", port: int = 18766, *, timeout: float = 2.0
) -> tuple[bool, dict[str, Any]]:
    """Check whether the optional local OpenAI-compatible gateway is already listening."""
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
    """Start optional `llm-router serve` detached in the background if requested."""
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


def _upsert_markdown_block(path: Path, body: str, *, dry_run: bool = False) -> str:
    existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    if _has_canary_guard(existing):
        return "skipped_ring0_canary"
    block = (
        "\n<!-- BEGIN LLM-PROVIDER-ROUTER-ORCHESTRATOR -->\n"
        + body.strip()
        + "\n<!-- END LLM-PROVIDER-ROUTER-ORCHESTRATOR -->\n"
    )
    cleaned = _ORCHESTRATOR_BLOCK_RE.sub("", existing).rstrip()
    updated = (cleaned + "\n" + block) if cleaned else block.lstrip("\n")
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        _backup_file(path)
        path.write_text(updated, encoding="utf-8")
    return "configured"


def wire_antigravity(
    home_dir: Path,
    python_exe: str,
    install_dir: Path,
    *,
    workspace_dir: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install always-on Antigravity rule & skill for OpenAI sub-agent delegation."""
    gemini_dir = Path(home_dir) / ".gemini"
    if not force and not gemini_dir.is_dir() and workspace_dir is None:
        return {"client": "antigravity", "status": "not_installed"}

    written: list[str] = []
    if force or gemini_dir.is_dir():
        rule_path = gemini_dir / "config" / "rules" / "llm-router-subagent.md"
        skill_path = gemini_dir / "config" / "skills" / "llm-router-subagent" / "SKILL.md"
        if not dry_run:
            rule_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            rule_path.write_text(
                render_antigravity_rule_file(python_exe, install_dir), encoding="utf-8"
            )
            skill_path.write_text(render_skill_file(python_exe, install_dir), encoding="utf-8")
        written.extend([str(rule_path), str(skill_path)])

    if workspace_dir is not None:
        ws_rule = Path(workspace_dir) / ".agents" / "rules" / "llm-router-subagent.md"
        if not dry_run:
            ws_rule.parent.mkdir(parents=True, exist_ok=True)
            ws_rule.write_text(
                render_antigravity_rule_file(python_exe, install_dir), encoding="utf-8"
            )
        written.append(str(ws_rule))

    return {"client": "antigravity", "status": "configured", "files": written, "dry_run": dry_run}


def wire_claude_code(
    home_dir: Path,
    python_exe: str,
    install_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Configure Claude Code `CLAUDE.md`, `agents/openai-worker.md`, and `SKILL.md`."""
    claude_dir = Path(home_dir) / ".claude"
    if not force and not claude_dir.is_dir():
        return {"client": "claude_code", "status": "not_installed"}

    claude_md = claude_dir / "CLAUDE.md"
    md_status = _upsert_markdown_block(
        claude_md, render_orchestrator_rule_body(python_exe, install_dir), dry_run=dry_run
    )
    agent_path = claude_dir / "agents" / "openai-worker.md"
    skill_path = claude_dir / "skills" / "llm-router-subagent" / "SKILL.md"
    if not dry_run:
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        agent_path.write_text(
            render_claude_subagent_file(python_exe, install_dir), encoding="utf-8"
        )
        skill_path.write_text(render_skill_file(python_exe, install_dir), encoding="utf-8")
    return {
        "client": "claude_code",
        "status": "configured",
        "claude_md_status": md_status,
        "files": [str(claude_md), str(agent_path), str(skill_path)],
        "dry_run": dry_run,
    }


def wire_codex(
    home_dir: Path,
    python_exe: str,
    install_dir: Path,
    gateway_url: str,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Configure Codex `AGENTS.md` rule (canary-safe) and `config.toml` provider profile."""
    codex_dir = Path(home_dir) / ".codex"
    if not force and not codex_dir.is_dir():
        return {"client": "codex", "status": "not_installed"}

    agents_md = codex_dir / "AGENTS.md"
    md_status = _upsert_markdown_block(
        agents_md, render_orchestrator_rule_body(python_exe, install_dir), dry_run=dry_run
    )

    cfg_path = codex_dir / "config.toml"
    existing = cfg_path.read_text(encoding="utf-8", errors="replace") if cfg_path.is_file() else ""
    toml_status = "already_configured"
    if "model_providers.llm_router" not in existing or "# BEGIN LLM-PROVIDER-ROUTER" in existing:
        block = (
            "\n# BEGIN LLM-PROVIDER-ROUTER\n"
            "[model_providers.llm_router]\n"
            'name = "LLM Provider Router"\n'
            f'base_url = "{gateway_url}"\n'
            'env_key = "OPENAI_API_KEY"\n'
            'wire_api = "chat"\n'
            "# END LLM-PROVIDER-ROUTER\n"
        )
        cleaned = _CODEX_TOML_BLOCK_RE.sub("", existing).rstrip()
        updated = (cleaned + "\n" + block) if cleaned else block.lstrip("\n")
        if not dry_run:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            _backup_file(cfg_path)
            cfg_path.write_text(updated, encoding="utf-8")
        toml_status = "configured"

    return {
        "client": "codex",
        "status": "configured",
        "agents_md_status": md_status,
        "config_toml_status": toml_status,
        "files": [str(agents_md), str(cfg_path)],
        "dry_run": dry_run,
    }


def wire_cursor(
    home_dir: Path,
    python_exe: str,
    install_dir: Path,
    *,
    workspace_dir: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install always-apply Cursor rule `.cursor/rules/llm-router-subagent.mdc`."""
    cursor_home = Path(home_dir) / ".cursor"
    if workspace_dir is None and not force and not cursor_home.is_dir():
        return {"client": "cursor", "status": "not_installed"}

    written: list[str] = []
    if workspace_dir is not None:
        ws_mdc = Path(workspace_dir) / ".cursor" / "rules" / "llm-router-subagent.mdc"
        if not dry_run:
            ws_mdc.parent.mkdir(parents=True, exist_ok=True)
            ws_mdc.write_text(render_cursor_mdc_file(python_exe, install_dir), encoding="utf-8")
        written.append(str(ws_mdc))
    if force or cursor_home.is_dir():
        home_mdc = cursor_home / "rules" / "llm-router-subagent.mdc"
        if not dry_run:
            home_mdc.parent.mkdir(parents=True, exist_ok=True)
            home_mdc.write_text(render_cursor_mdc_file(python_exe, install_dir), encoding="utf-8")
        written.append(str(home_mdc))

    return {"client": "cursor", "status": "configured", "files": written, "dry_run": dry_run}


def wire_shell_env(
    home_dir: Path,
    *,
    install_dir: Path,
    python_exe: str,
    dry_run: bool = False,
    posix_only_for_test: bool = False,
) -> dict[str, Any]:
    """Persist `LLM_ROUTER_*` env vars cleanly without overwriting unrelated OpenAI/Claude keys."""
    global_env = str(default_global_env_path())
    if os.name == "nt" and not posix_only_for_test:
        if dry_run:
            return {"client": "windows_user_env", "status": "dry_run"}
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
            ) as reg:
                winreg.SetValueEx(reg, "LLM_ROUTER_HOME", 0, winreg.REG_SZ, str(install_dir))
                winreg.SetValueEx(reg, "LLM_ROUTER_PYTHON", 0, winreg.REG_SZ, str(python_exe))
                winreg.SetValueEx(reg, "LLM_ROUTER_ENV_FILE", 0, winreg.REG_SZ, global_env)
            return {
                "client": "windows_user_env",
                "status": "configured",
                "vars": ["LLM_ROUTER_HOME", "LLM_ROUTER_PYTHON", "LLM_ROUTER_ENV_FILE"],
            }
        except OSError as exc:
            return {"client": "windows_user_env", "status": "error", "error": str(exc)}

    home = Path(home_dir)
    rc_targets = [home / ".bashrc", home / ".zshrc"]
    block = (
        "\n# >>> llm-provider-router >>>\n"
        f'export LLM_ROUTER_HOME="{install_dir}"\n'
        f'export LLM_ROUTER_PYTHON="{python_exe}"\n'
        f'export LLM_ROUTER_ENV_FILE="{global_env}"\n'
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
    workspace_dir: Path | None = None,
    python_exe: str | None = None,
    start_gateway: bool = False,
    clients: str = "auto",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Auto-wire Orchestrator rules/skills across Antigravity, Claude Code, Codex, and Cursor."""
    cfg = RouterConfig.from_env(env_file=env_file)
    host = cfg.gateway_host
    port = cfg.gateway_port
    gateway_url = f"http://{host}:{port}/v1"

    resolved_home = Path(home_dir) if home_dir is not None else Path.home()
    resolved_install = Path(install_dir) if install_dir is not None else Path.cwd()
    resolved_ws = Path(workspace_dir) if workspace_dir is not None else None
    eff_python = _resolve_python_exe(resolved_install, python_exe)

    eff_env = env_file
    if eff_env is None:
        cand = resolved_install / ".env"
        if cand.is_file():
            eff_env = cand
        elif default_global_env_path().is_file():
            eff_env = default_global_env_path()

    gateway_status: dict[str, Any] = {"running": False, "skipped": True}
    if start_gateway and not dry_run:
        gateway_status = ensure_gateway_running(
            host=host, port=port, env_file=eff_env, python_exe=eff_python
        )

    requested = {item.strip().lower() for item in clients.split(",") if item.strip()}
    run_all = "auto" in requested or "all" in requested
    explicit = not run_all

    auto_connected: list[dict[str, Any]] = []
    if run_all or "env" in requested or "shell" in requested:
        auto_connected.append(
            wire_shell_env(
                resolved_home, install_dir=resolved_install, python_exe=eff_python, dry_run=dry_run
            )
        )
    if run_all or "agy" in requested or "antigravity" in requested:
        auto_connected.append(
            wire_antigravity(
                resolved_home,
                eff_python,
                resolved_install,
                workspace_dir=resolved_ws,
                force=explicit,
                dry_run=dry_run,
            )
        )
    if run_all or "claude" in requested or "claude_code" in requested:
        auto_connected.append(
            wire_claude_code(
                resolved_home,
                eff_python,
                resolved_install,
                force=explicit,
                dry_run=dry_run,
            )
        )
    if run_all or "codex" in requested:
        auto_connected.append(
            wire_codex(
                resolved_home,
                eff_python,
                resolved_install,
                gateway_url,
                force=explicit,
                dry_run=dry_run,
            )
        )
    if run_all or "cursor" in requested:
        auto_connected.append(
            wire_cursor(
                resolved_home,
                eff_python,
                resolved_install,
                workspace_dir=resolved_ws,
                force=explicit,
                dry_run=dry_run,
            )
        )

    delegate_cmd = f'"{eff_python}" -m llm_provider_router delegate'
    return {
        "ok": True,
        "orchestrator_mode": "orchestrator_plus_openai_subagent",
        "python_exe": eff_python,
        "install_dir": str(resolved_install),
        "delegate_command": delegate_cmd,
        "verification_command": (
            f'{delegate_cmd} --role writing "Confirm OpenAI sub-agent routing is active" --json'
        ),
        "gateway_url": gateway_url if start_gateway else None,
        "gateway": gateway_status,
        "auto_connected": auto_connected,
    }
