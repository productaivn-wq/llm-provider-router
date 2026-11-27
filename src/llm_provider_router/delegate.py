"""Sub-agent task delegation (`delegate` & `batch`) routed to OpenAI models via `LLMProviderRouter`."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import _read_text_auto_encoding, redact_secrets
from .providers import AllProvidersFailedError
from .router import LLMProviderRouter

MAX_CONTEXT_BYTES_PER_FILE = 256 * 1024


@dataclass(frozen=True)
class RolePreset:
    """Role-specific OpenAI worker profile used by `delegate` and `batch`."""

    name: str
    for_coding: bool
    system_prompt: str


ROLE_PRESETS: dict[str, RolePreset] = {
    "general": RolePreset(
        name="general",
        for_coding=False,
        system_prompt=(
            "You are a focused OpenAI execution sub-agent invoked by a parent orchestrator. "
            "Complete the delegated task accurately, concisely, and match the language of the request."
        ),
    ),
    "writing": RolePreset(
        name="writing",
        for_coding=False,
        system_prompt=(
            "You are a clear drafting and summarization OpenAI sub-agent. "
            "Produce well-structured, direct output in the language of the request without meta-chatter."
        ),
    ),
    "analysis": RolePreset(
        name="analysis",
        for_coding=False,
        system_prompt=(
            "You are an analytical synthesis OpenAI sub-agent. "
            "Extract key facts, risks, comparisons, and structured takeaways grounded in the provided input."
        ),
    ),
    "coding": RolePreset(
        name="coding",
        for_coding=True,
        system_prompt=(
            "You are a senior software engineering OpenAI sub-agent. "
            "Return clean, production-grade code or patches with concise explanations grounded in the supplied context."
        ),
    ),
    "review": RolePreset(
        name="review",
        for_coding=True,
        system_prompt=(
            "You are a strict code and specification reviewer OpenAI sub-agent. "
            "Identify concrete correctness, security, edge-case, and regression issues concisely."
        ),
    ),
}


def _build_context_block(context_files: list[str | Path] | None) -> str:
    if not context_files:
        return ""
    sections: list[str] = []
    for raw_path in context_files:
        p = Path(raw_path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"Context file not found: {p}")
        text = _read_text_auto_encoding(p)
        if len(text.encode("utf-8", errors="replace")) > MAX_CONTEXT_BYTES_PER_FILE:
            text = text[: MAX_CONTEXT_BYTES_PER_FILE // 2] + "\n...[truncated]..."
        sections.append(f"=== FILE: {p.name} ===\n{text}")
    return "\n\n".join(sections)


def run_delegate(
    task: str,
    *,
    role: str = "general",
    context_files: list[str | Path] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
    env_file: str | Path | None = None,
    router: LLMProviderRouter | None = None,
) -> dict[str, Any]:
    """Delegate a single sub-agent task to OpenAI/LiteLLM via `LLMProviderRouter`."""
    norm_role = (role or "general").strip().lower()
    preset = ROLE_PRESETS.get(norm_role)
    if preset is None:
        valid = ", ".join(sorted(ROLE_PRESETS))
        raise ValueError(f"Unknown delegate role {role!r}; choose from: {valid}")

    cleaned_task = str(task or "").strip()
    if not cleaned_task:
        raise ValueError("Delegated task prompt must be non-empty")

    ctx_block = _build_context_block(context_files)
    full_prompt = f"{cleaned_task}\n\n{ctx_block}" if ctx_block else cleaned_task
    eff_system = (system_prompt or "").strip() or preset.system_prompt

    owns_router = router is None
    active_router = router or LLMProviderRouter(env_file=env_file)
    try:
        res = active_router.complete(
            full_prompt,
            system_prompt=eff_system,
            model=model,
            for_coding=preset.for_coding,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return {
            "ok": True,
            "role": norm_role,
            "provider": res.provider,
            "model": res.model,
            "content": res.content,
            "usage": {
                "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
                "total_tokens": res.total_tokens,
            },
            "latency_ms": round(res.latency_ms, 2),
        }
    except AllProvidersFailedError as exc:
        return {
            "ok": False,
            "role": norm_role,
            "error": redact_secrets(str(exc)),
        }
    finally:
        if owns_router:
            active_router.close()


def run_batch(
    tasks: list[dict[str, Any]],
    *,
    max_workers: int = 4,
    env_file: str | Path | None = None,
    router: LLMProviderRouter | None = None,
) -> dict[str, Any]:
    """Execute multiple independent sub-agent tasks in parallel and preserve input order."""
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("tasks must be a non-empty list of objects")

    owns_router = router is None
    active_router = router or LLMProviderRouter(env_file=env_file)
    workers = max(1, min(8, int(max_workers or 4)))

    def _run_one(idx: int, item: dict[str, Any]) -> dict[str, Any]:
        task_id = str(item.get("id") or f"task-{idx + 1}")
        prompt = str(item.get("task") or item.get("prompt") or "").strip()
        role = str(item.get("role") or "general")
        ctx = item.get("context_files")
        sys_p = item.get("system") or item.get("system_prompt")
        mod = item.get("model")
        max_tok = item.get("max_tokens")
        timeout_val = item.get("timeout")
        try:
            out = run_delegate(
                prompt,
                role=role,
                context_files=ctx if isinstance(ctx, list) else None,
                system_prompt=str(sys_p) if sys_p else None,
                model=str(mod) if mod else None,
                max_tokens=int(max_tok) if max_tok is not None else None,
                timeout=float(timeout_val) if timeout_val is not None else None,
                router=active_router,
            )
            out["id"] = task_id
            return out
        except (OSError, ValueError) as exc:
            return {"id": task_id, "ok": False, "role": role, "error": redact_secrets(str(exc))}

    try:
        ordered_results: list[dict[str, Any] | None] = [None] * len(tasks)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            fut_map = {pool.submit(_run_one, idx, item): idx for idx, item in enumerate(tasks)}
            for fut in concurrent.futures.as_completed(fut_map):
                idx = fut_map[fut]
                ordered_results[idx] = fut.result()

        final_results = [r if r is not None else {"ok": False} for r in ordered_results]
        succeeded = sum(1 for r in final_results if r.get("ok"))
        failed = len(final_results) - succeeded
        return {
            "ok": failed == 0,
            "total": len(final_results),
            "succeeded": succeeded,
            "failed": failed,
            "results": final_results,
        }
    finally:
        if owns_router:
            active_router.close()
