"""One Strands agent per conversation.

A Strands ``Agent`` carries its own message history, so sharing a single
instance across callers mixes their conversations — user B's answer can be
built from user A's context — and overlapping requests raise
``ConcurrencyException``. Keep one agent per session id instead, bounded and
idle-expiring so a long-lived container cannot grow without limit.

The cache lives in one container's memory: it is lost on redeploy and is not
shared if AgentCore scales out. Durable memory across sessions is what
AgentCore Memory is for.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock
from typing import Any

from fpl_agent.agent import build_agent

SESSION_TTL_SECONDS = 30 * 60
MAX_SESSIONS = 100

# session_id -> (last_seen_monotonic, agent). Ordered least- to most-recent.
_sessions: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_lock = Lock()


def agent_for(session_id: str | None) -> Any:
    """Return the agent for this conversation, creating one if needed.

    With no session id, return a throwaway agent rather than reusing a shared
    "anonymous" one — a common bucket would recreate the cross-user leak this
    module exists to prevent.
    """
    if not session_id:
        return build_agent()

    now = time.monotonic()
    with _lock:
        _evict_idle(now)
        entry = _sessions.pop(session_id, None)
        agent = entry[1] if entry is not None else build_agent()
        _sessions[session_id] = (now, agent)  # re-insert as most recent
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)  # drop least recently used
        return agent


def _evict_idle(now: float) -> None:
    """Forget conversations nobody has touched for SESSION_TTL_SECONDS."""
    for sid, (last_seen, _) in list(_sessions.items()):
        if now - last_seen > SESSION_TTL_SECONDS:
            del _sessions[sid]


def active_sessions() -> int:
    """How many conversations are currently held (diagnostics, tests)."""
    with _lock:
        return len(_sessions)


def reset() -> None:
    """Drop every cached conversation."""
    with _lock:
        _sessions.clear()
