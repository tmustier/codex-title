#!/usr/bin/env python3
"""Wrapper to run Codex with automatic terminal tab title updates."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_RUNNING = "codex:running..."
DEFAULT_DONE = "codex:✅"
DEFAULT_NEW = "codex:new"
DEFAULT_CONFIG = Path.home() / ".config" / "codex-title" / "config.env"
DEFAULT_NO_COMMIT_TITLE = "codex:🚧"
TUI_LOG_PATH = Path.home() / ".codex" / "log" / "codex-tui.log"
HISTORY_LOG_PATH = Path.home() / ".codex" / "history.jsonl"
_TUI_RESUME_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2}T[0-9:.]+Z)\s+INFO Resum(?:ing|ed) rollout(?: successfully)? from "(?P<path>[^"]+)"'
)
_BOOTSTRAP_PREFIXES = ("# AGENTS.md instructions", "<environment_context>")
_COMMAND_SEPARATORS = {";", "&&", "||", "|", "&"}
_RESUME_PREFIXES = ("/resume", "/last")
_EXIT_CODE_RE = re.compile(r"Exit code:\s*(\d+)")
_PROCESS_EXIT_RE = re.compile(r"Process exited with code\s+(\d+)")
_JSON_EXIT_CODE_RE = re.compile(r'"exit_code"\s*:\s*(\d+)')
_LOG_LOCK = threading.Lock()
_LOG_PATH_RAW = os.environ.get("CODEX_TITLE_LOG_PATH")
if _LOG_PATH_RAW is None:
    _LOG_PATH: Path | None = Path.home() / ".codex" / "log" / "codex-title.log"
elif _LOG_PATH_RAW.strip() == "":
    _LOG_PATH = None
else:
    _LOG_PATH = Path(_LOG_PATH_RAW).expanduser()
_FOLLOW_GLOBAL_RESUME_RAW = os.environ.get("CODEX_TITLE_FOLLOW_GLOBAL_RESUME", "")
_FOLLOW_GLOBAL_RESUME = _FOLLOW_GLOBAL_RESUME_RAW.strip().lower() in {"1", "true", "yes", "on"}
_IDLE_DONE_RAW = os.environ.get("CODEX_TITLE_IDLE_DONE_SECS")
try:
    _IDLE_DONE_SECS = float(_IDLE_DONE_RAW) if _IDLE_DONE_RAW is not None else 3.0
except ValueError:
    _IDLE_DONE_SECS = 3.0
if _IDLE_DONE_SECS < 0:
    _IDLE_DONE_SECS = 0.0
_CLOCK_SKEW_RAW = os.environ.get("CODEX_TITLE_CLOCK_SKEW_SECS")
try:
    _CLOCK_SKEW_SECS = float(_CLOCK_SKEW_RAW) if _CLOCK_SKEW_RAW is not None else 300.0
except ValueError:
    _CLOCK_SKEW_SECS = 300.0
if _CLOCK_SKEW_SECS < 0:
    _CLOCK_SKEW_SECS = 0.0
_PID_LOG_TIMEOUT_RAW = os.environ.get("CODEX_TITLE_PID_LOG_TIMEOUT_SECS")
try:
    _PID_LOG_TIMEOUT_SECS = float(_PID_LOG_TIMEOUT_RAW) if _PID_LOG_TIMEOUT_RAW is not None else 8.0
except ValueError:
    _PID_LOG_TIMEOUT_SECS = 8.0
if _PID_LOG_TIMEOUT_SECS < 0:
    _PID_LOG_TIMEOUT_SECS = 0.0


def _read_kv_config(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def _resolve_config_path(cli_args: list[str]) -> Path:
    env_path = os.environ.get("CODEX_TITLE_CONFIG")
    default = Path(env_path).expanduser() if env_path else DEFAULT_CONFIG
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=Path)
    known, _ = parser.parse_known_args(cli_args)
    if known.config:
        return known.config.expanduser()
    return default


def _resolve_defaults(cli_args: list[str]) -> dict[str, str]:
    config_path = _resolve_config_path(cli_args)
    config = _read_kv_config(config_path)

    def pick(env_key: str, config_key: str, fallback: str) -> str:
        return os.environ.get(env_key) or config.get(config_key) or fallback

    return {
        "config_path": str(config_path),
        "new_title": pick("CODEX_TITLE_NEW_TITLE", "new_title", DEFAULT_NEW),
        "running_title": pick("CODEX_TITLE_RUNNING_TITLE", "running_title", DEFAULT_RUNNING),
        "done_title": pick("CODEX_TITLE_DONE_TITLE", "done_title", DEFAULT_DONE),
        "no_commit_title": pick("CODEX_TITLE_NO_COMMIT_TITLE", "no_commit_title", DEFAULT_NO_COMMIT_TITLE),
    }


def _git_repo_root(path: Path) -> Path | None:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    root = output.decode().strip()
    return Path(root) if root else None


def _git_head(repo_root: Path) -> str | None:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    head = output.decode().strip()
    return head or None


def _git_commit_in_range(repo_root: Path, start_ts: float, end_ts: float) -> bool:
    if end_ts < start_ts:
        start_ts, end_ts = end_ts, start_ts
    start = datetime.fromtimestamp(start_ts, timezone.utc).isoformat()
    end = datetime.fromtimestamp(end_ts, timezone.utc).isoformat()
    try:
        output = subprocess.check_output(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                "--format=%H",
                f"--since={start}",
                f"--until={end}",
                "-1",
            ],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False
    return bool(output.strip())


def _log_debug(message: str) -> None:
    if _LOG_PATH is None:
        return
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return
    try:
        stamp = datetime.now(timezone.utc).isoformat()
        line = f"{stamp} {message}\n"
        with _LOG_LOCK:
            with _LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(line)
    except Exception:
        return


class DoneState:
    def __init__(self) -> None:
        self.seen = False


class TitleWriter:
    def __init__(self) -> None:
        self._stream = None
        try:
            self._stream = open("/dev/tty", "wb", buffering=0)
        except Exception:
            self._stream = getattr(sys.stdout, "buffer", sys.stdout)

    def set(self, title: str) -> None:
        seq = f"\033]0;{title}\007"
        try:
            if isinstance(self._stream, (io.BufferedIOBase, io.RawIOBase)):
                self._stream.write(seq.encode("utf-8", errors="ignore"))
            else:
                self._stream.write(seq)
            self._stream.flush()
        except Exception:
            pass


def _parse_timestamp(event: dict) -> float | None:
    ts = event.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        if ts.endswith("Z"):
            ts = f"{ts[:-1]}+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _parse_iso_timestamp(value: str) -> float | None:
    try:
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _parse_history_ts(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _log_path_from_pid(pid: int) -> Path | None:
    if pid <= 0:
        return None
    try:
        output = subprocess.check_output(
            ["lsof", "-p", str(pid), "-Fn"],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    candidates: list[Path] = []
    for raw in output.decode(errors="ignore").splitlines():
        if not raw.startswith("n"):
            continue
        path_str = raw[1:]
        if "rollout-" not in path_str or not path_str.endswith(".jsonl"):
            continue
        path = Path(path_str)
        if not path.exists():
            continue
        if path.name.startswith("rollout-"):
            candidates.append(path)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    latest: tuple[float, Path] | None = None
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if latest is None or mtime > latest[0]:
            latest = (mtime, path)
    return latest[1] if latest else None


def _timestamp_trustworthy(ts: float | None, reference: float) -> bool:
    if ts is None:
        return False
    if _CLOCK_SKEW_SECS <= 0:
        return True
    return abs(ts - reference) <= _CLOCK_SKEW_SECS


def _history_start_offset() -> int:
    try:
        return HISTORY_LOG_PATH.stat().st_size
    except FileNotFoundError:
        return 0


def _history_has_session(session_id: str, limit: int | None = None) -> bool:
    if not HISTORY_LOG_PATH.exists():
        return False
    if limit is None:
        try:
            with HISTORY_LOG_PATH.open(encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    data = _parse_json(line)
                    if data is None:
                        continue
                    if data.get("session_id") == session_id:
                        return True
        except Exception:
            return False
        return False
    for line in reversed(_tail_lines(HISTORY_LOG_PATH, limit)):
        data = _parse_json(line)
        if data is None:
            continue
        if data.get("session_id") == session_id:
            return True
    return False


def _latest_history_session_id(history_log: Path) -> str | None:
    for line in reversed(_tail_lines(history_log, 200)):
        data = _parse_json(line)
        if data is None:
            continue
        session_id = data.get("session_id")
        if isinstance(session_id, str):
            return session_id
    return None


def _tail_lines(path: Path, limit: int) -> list[str]:
    lines: deque[str] = deque(maxlen=limit)
    try:
        with path.open(encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                lines.append(line.rstrip("\n"))
    except Exception:
        return []
    return list(lines)


def _is_bootstrap_message(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith(_BOOTSTRAP_PREFIXES)


def _is_resume_command(text: str | None) -> bool:
    if not text:
        return False
    return text.lstrip().lower().startswith(_RESUME_PREFIXES)


def _extract_user_text(etype: str, payload: dict) -> str | None:
    if etype == "event_msg":
        if payload.get("type") == "user_message":
            message = payload.get("message")
            if isinstance(message, str):
                return message
    if etype == "response_item" and payload.get("type") == "message":
        if payload.get("role") == "user":
            content = payload.get("content")
            if isinstance(content, list) and content:
                entry = content[0]
                if isinstance(entry, dict):
                    text = entry.get("text") or entry.get("input_text")
                    if isinstance(text, str):
                        return text
    return None


def _is_git_token(token: str) -> bool:
    if token == "git":
        return True
    try:
        return Path(token).name == "git"
    except Exception:
        return False


def _segment_has_git_commit(tokens: list[str]) -> bool:
    for idx, token in enumerate(tokens):
        if _is_git_token(token):
            if "commit" in tokens[idx + 1 :]:
                return True
    return False


def _command_has_git_commit(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except Exception:
        return "git commit" in command
    segment: list[str] = []
    for token in tokens:
        if token in _COMMAND_SEPARATORS:
            if _segment_has_git_commit(segment):
                return True
            segment = []
            continue
        segment.append(token)
    return _segment_has_git_commit(segment)


def _parse_exit_code(output: str) -> int | None:
    for pattern in (_EXIT_CODE_RE, _PROCESS_EXIT_RE, _JSON_EXIT_CODE_RE):
        match = pattern.search(output)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _extract_command(payload: dict) -> str | None:
    if payload.get("type") != "function_call":
        return None
    name = payload.get("name")
    if name not in {"shell_command", "exec_command"}:
        return None
    args = payload.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return None
    if not isinstance(args, dict):
        return None
    cmd = args.get("command") or args.get("cmd")
    return cmd if isinstance(cmd, str) else None


def _note_tool_call(resp_type: str | None, payload: dict, pending_calls: set[str]) -> None:
    if resp_type in {"function_call", "custom_tool_call"}:
        call_id = payload.get("call_id")
        if isinstance(call_id, str):
            if payload.get("status") == "completed":
                pending_calls.discard(call_id)
            else:
                pending_calls.add(call_id)
        return
    if resp_type in {"function_call_output", "custom_tool_call_output"}:
        call_id = payload.get("call_id")
        if isinstance(call_id, str):
            pending_calls.discard(call_id)


def _should_idle_done(
    pending_user: bool,
    real_user_seen: bool,
    pending_tool_calls: set[str],
    last_response_activity: float | None,
    now: float,
    idle_timeout: float,
) -> bool:
    if idle_timeout <= 0:
        return False
    if not pending_user or not real_user_seen:
        return False
    if pending_tool_calls:
        return False
    if last_response_activity is None:
        return False
    return now - last_response_activity >= idle_timeout


def iter_jsonl(
    path: Path,
    stop_event: threading.Event,
    start_time: float | None,
    switch_state: "SwitchState | None" = None,
    start_offset: int | None = None,
    idle_interval: float | None = None,
) -> Iterable[dict]:
    with path.open(encoding="utf-8") as handle:
        if start_offset is not None:
            try:
                if start_offset > 0:
                    handle.seek(start_offset)
                    handle.readline()
                else:
                    handle.seek(0)
            except Exception:
                handle.seek(0)
        for line in handle:
            data = _parse_json(line)
            if data is not None and _should_emit(data, start_time):
                if switch_state is not None:
                    switch_state.note_activity()
                if idle_interval is not None and idle_interval > 0:
                    last_idle = time.monotonic()
                yield data
            if switch_state is not None:
                switch_state.maybe_switch()
                if switch_state.next_path is not None:
                    return
        last_idle = time.monotonic()
        while not stop_event.is_set():
            line = handle.readline()
            if not line:
                time.sleep(0.1)
                if switch_state is not None:
                    switch_state.maybe_switch()
                    if switch_state.next_path is not None:
                        return
                if idle_interval is not None and idle_interval > 0:
                    now = time.monotonic()
                    if now - last_idle >= idle_interval:
                        last_idle = now
                        yield {"type": "_idle"}
                continue
            data = _parse_json(line)
            if data is not None and _should_emit(data, start_time):
                if switch_state is not None:
                    switch_state.note_activity()
                if idle_interval is not None and idle_interval > 0:
                    last_idle = time.monotonic()
                yield data
            if switch_state is not None:
                switch_state.maybe_switch()
                if switch_state.next_path is not None:
                    return


def _parse_json(line: str) -> dict | None:
    try:
        return json.loads(line)
    except Exception:
        return None


def _should_emit(event: dict, start_time: float | None) -> bool:
    if start_time is None:
        return True
    ts = _parse_timestamp(event)
    if ts is None:
        return False
    if not _timestamp_trustworthy(ts, start_time):
        return True
    return ts >= start_time


def _collect_log_state(
    log_path: Path,
    history_seen: bool,
) -> tuple[bool, bool, float | None, float | None, bool]:
    pending_user = False
    seen_assistant = False
    last_user_ts: float | None = None
    last_assistant_ts: float | None = None
    real_user_seen = history_seen
    pending_commit_calls: dict[str, bool] = {}
    pending_tool_calls: set[str] = set()
    turn_commit_seen = False
    last_turn_commit = False
    response_seen = False
    last_response_ts: float | None = None

    def note_response(ts: float | None) -> None:
        nonlocal response_seen, last_response_ts
        response_seen = True
        if ts is not None:
            last_response_ts = ts

    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            data = _parse_json(line)
            if data is None:
                continue
            ts = _parse_timestamp(data)
            etype = data.get("type")
            payload = data.get("payload") or {}
            user_text = _extract_user_text(etype, payload)
            if user_text is not None:
                if not real_user_seen and _is_bootstrap_message(user_text):
                    continue
                real_user_seen = True
                pending_user = True
                response_seen = False
                pending_tool_calls.clear()
                turn_commit_seen = False
                pending_commit_calls.clear()
                if ts is not None:
                    last_user_ts = ts
                continue
            if etype == "response_item":
                resp_type = payload.get("type")
                _note_tool_call(resp_type, payload, pending_tool_calls)
                if resp_type == "function_call":
                    cmd = _extract_command(payload)
                    if cmd and _command_has_git_commit(cmd):
                        call_id = payload.get("call_id")
                        if isinstance(call_id, str):
                            pending_commit_calls[call_id] = True
                elif resp_type == "function_call_output":
                    call_id = payload.get("call_id")
                    if isinstance(call_id, str) and pending_commit_calls.pop(call_id, None):
                        output = payload.get("output")
                        if isinstance(output, str) and _parse_exit_code(output) == 0:
                            turn_commit_seen = True
                if resp_type == "message":
                    if payload.get("role") == "assistant":
                        pending_user = False
                        seen_assistant = True
                        last_turn_commit = turn_commit_seen
                        if ts is not None:
                            last_assistant_ts = ts
                        note_response(ts)
                elif resp_type is not None:
                    note_response(ts)
            if etype == "event_msg":
                msg_type = payload.get("type")
                if msg_type and msg_type != "user_message":
                    note_response(ts)
                if msg_type in {"agent_message", "assistant_message", "turn_aborted"}:
                    pending_user = False
                    seen_assistant = True
                    last_turn_commit = turn_commit_seen
                    if ts is not None:
                        last_assistant_ts = ts
    if pending_user and real_user_seen and response_seen and not pending_tool_calls:
        idle_timeout = _IDLE_DONE_SECS
        if idle_timeout > 0 and last_response_ts is not None:
            now = time.time()
            if _timestamp_trustworthy(last_response_ts, now):
                if now - last_response_ts >= idle_timeout:
                    pending_user = False
                    seen_assistant = True
                    last_turn_commit = turn_commit_seen
                    if last_assistant_ts is None:
                        last_assistant_ts = last_response_ts
    return pending_user, seen_assistant, last_user_ts, last_assistant_ts, last_turn_commit


def _initial_title_from_log(
    log_path: Path,
    running_title: str,
    done_title: str,
    no_commit_title: str,
    allow_unseen: bool = False,
) -> str | None:
    try:
        session_id = _session_id_from_log(log_path)
        history_seen = session_id is None or _history_has_session(session_id)
        if session_id and not history_seen and not allow_unseen:
            return None
        pending_user, seen_assistant, last_user_ts, last_assistant_ts, last_turn_commit = _collect_log_state(
            log_path,
            history_seen,
        )
    except Exception:
        return None
    if pending_user:
        return running_title
    if not seen_assistant:
        return None
    if last_turn_commit:
        return done_title
    if (
        no_commit_title
        and last_user_ts is not None
        and last_assistant_ts is not None
        and (commit_root := _git_repo_root(Path.cwd()))
    ):
        if _git_commit_in_range(commit_root, last_user_ts, last_assistant_ts):
            return done_title
        return no_commit_title
    return done_title


def _logs_by_mtime(session_dir: Path) -> list[Path]:
    paths: list[tuple[float, Path]] = []
    for path in session_dir.glob("rollout-*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        paths.append((mtime, path))
    return [path for _, path in sorted(paths, reverse=True)]


def _initial_title_from_recent_logs(
    session_dir: Path,
    skip: Path,
    running_title: str,
    done_title: str,
    no_commit_title: str,
    allow_unseen: bool = False,
    limit: int = 5,
) -> str | None:
    count = 0
    for path in _logs_by_mtime(session_dir):
        if path == skip:
            continue
        initial_title = _initial_title_from_log(
            path,
            running_title,
            done_title,
            no_commit_title,
            allow_unseen=allow_unseen,
        )
        if initial_title:
            return initial_title
        count += 1
        if count >= limit:
            break
    return None


def session_dir_for_time(epoch: float) -> Path:
    tm = time.localtime(epoch)
    return (
        Path.home()
        / ".codex"
        / "sessions"
        / f"{tm.tm_year:04d}"
        / f"{tm.tm_mon:02d}"
        / f"{tm.tm_mday:02d}"
    )


def _latest_log(session_dir: Path) -> Path | None:
    if not session_dir.exists():
        return None
    latest: tuple[float, Path] | None = None
    for path in session_dir.glob("rollout-*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if latest is None or mtime > latest[0]:
            latest = (mtime, path)
    return latest[1] if latest else None


def _log_matches_cwd(path: Path, cwd: Path) -> bool:
    target = str(cwd)
    try:
        with path.open(encoding="utf-8") as handle:
            for _ in range(200):
                line = handle.readline()
                if not line:
                    break
                data = _parse_json(line)
                if data is None:
                    continue
                if data.get("type") == "session_meta":
                    payload = data.get("payload") or {}
                    return payload.get("cwd") == target
                if data.get("type") == "turn_context":
                    payload = data.get("payload") or {}
                    if payload.get("cwd") == target:
                        return True
    except Exception:
        return False
    return False


def _session_id_from_log(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8") as handle:
            for _ in range(200):
                line = handle.readline()
                if not line:
                    break
                data = _parse_json(line)
                if data is None:
                    continue
                if data.get("type") == "session_meta":
                    payload = data.get("payload") or {}
                    session_id = payload.get("id")
                    if isinstance(session_id, str):
                        return session_id
    except Exception:
        return None
    return None


def _session_meta_timestamp(path: Path) -> float | None:
    try:
        with path.open(encoding="utf-8") as handle:
            for _ in range(200):
                line = handle.readline()
                if not line:
                    break
                data = _parse_json(line)
                if data is None:
                    continue
                if data.get("type") == "session_meta":
                    payload = data.get("payload") or {}
                    ts = payload.get("timestamp") or data.get("timestamp")
                    if isinstance(ts, str):
                        return _parse_iso_timestamp(ts)
    except Exception:
        return None
    return None


def _best_log_candidate(
    candidates: list[tuple[float, Path]],
    start_time: float,
    cwd: Path,
) -> Path | None:
    best_key: tuple[int, float, float] | None = None
    best_path: Path | None = None
    for mtime, path in candidates:
        meta_ts = _session_meta_timestamp(path)
        if meta_ts is not None and not _timestamp_trustworthy(meta_ts, start_time):
            meta_ts = None
        candidate_ts = meta_ts if meta_ts is not None else mtime
        distance = abs(candidate_ts - start_time)
        cwd_match = _log_matches_cwd(path, cwd)
        key = (0 if cwd_match else 1, distance, -mtime)
        if best_key is None or key < best_key:
            best_key = key
            best_path = path
    return best_path


def _find_log_by_session_id(root: Path, session_id: str, cwd: Path) -> Path | None:
    if not root.exists():
        return None
    matches: list[tuple[float, Path]] = []
    for path in root.rglob(f"*{session_id}.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        matches.append((mtime, path))
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0][1]
    best_cwd: tuple[float, Path] | None = None
    for mtime, path in matches:
        if _log_matches_cwd(path, cwd):
            if best_cwd is None or mtime > best_cwd[0]:
                best_cwd = (mtime, path)
    if best_cwd:
        return best_cwd[1]
    return max(matches, key=lambda item: item[0])[1]


def _resume_log_from_tui(tui_log: Path, cwd: Path) -> Path | None:
    fallback: Path | None = None
    for line in reversed(_tail_lines(tui_log, 1000)):
        match = _TUI_RESUME_RE.match(line)
        if not match:
            continue
        path = Path(match.group("path"))
        if not path.exists():
            continue
        if _log_matches_cwd(path, cwd):
            _log_debug(f"resume:tui path={path}")
            return path
        if fallback is None:
            fallback = path
    if fallback is not None:
        _log_debug(f"resume:tui fallback path={fallback}")
    return fallback


def _recent_log_any(root: Path, since: float, cwd: Path) -> Path | None:
    best_any: tuple[float, Path] | None = None
    best_cwd: tuple[float, Path] | None = None
    if not root.exists():
        return None
    for path in root.rglob("rollout-*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime < since:
            continue
        if best_any is None or mtime > best_any[0]:
            best_any = (mtime, path)
        if _log_matches_cwd(path, cwd):
            if best_cwd is None or mtime > best_cwd[0]:
                best_cwd = (mtime, path)
    return best_cwd[1] if best_cwd else (best_any[1] if best_any else None)


def _status_log_path(session_dir: Path, cwd: Path) -> tuple[Path | None, str | None]:
    resume_path = _resume_log_from_tui(TUI_LOG_PATH, cwd)
    if resume_path:
        return resume_path, "tui"
    if HISTORY_LOG_PATH.exists():
        session_id = _latest_history_session_id(HISTORY_LOG_PATH)
        if session_id:
            path = _find_log_by_session_id(Path.home() / ".codex" / "sessions", session_id, cwd)
            if path:
                return path, "history"
    latest = _latest_log(session_dir)
    if latest:
        return latest, "session_dir"
    recent = _recent_log_any(Path.home() / ".codex" / "sessions", 0.0, cwd)
    if recent:
        return recent, "recent_any"
    return None, None


class SwitchState:
    def __init__(
        self,
        log_path: Path,
        sessions_root: Path,
        cwd: Path,
        start_time: float,
        switch_after: float = 1.0,
        allow_external_switch: bool = False,
    ) -> None:
        self.log_path = log_path
        self.sessions_root = sessions_root
        self.cwd = cwd
        self.start_time = start_time
        self.switch_after = switch_after
        self.session_id = _session_id_from_log(log_path)
        self.pinned_path: Path | None = None
        self.allow_external_switch = allow_external_switch
        self.last_activity = time.time()
        self.last_check = 0.0
        self.next_path: Path | None = None
        self.tui_log_mtime = 0.0
        self.history_mtime = 0.0
        self.history_offset = _history_start_offset()

    def note_activity(self) -> None:
        self.last_activity = time.time()

    def maybe_switch(self) -> None:
        if self.next_path is not None:
            return
        if not self.allow_external_switch:
            return
        now = time.time()
        if now - self.last_check < 0.5:
            return
        self.last_check = now
        candidate = self._tui_resume_candidate()
        if candidate:
            if self.pinned_path != candidate:
                self.pinned_path = candidate
                _log_debug(f"pin:tui path={candidate}")
            if candidate != self.log_path:
                _log_debug(f"switch:tui from={self.log_path} to={candidate}")
                self.next_path = candidate
            return
        candidate = self._history_candidate()
        if candidate:
            if self.pinned_path != candidate:
                self.pinned_path = candidate
                _log_debug(f"pin:history path={candidate}")
            if candidate != self.log_path:
                _log_debug(f"switch:history from={self.log_path} to={candidate}")
                self.next_path = candidate
            return
        if self.pinned_path is not None:
            if self.log_path != self.pinned_path:
                _log_debug(f"switch:pin from={self.log_path} to={self.pinned_path}")
                self.next_path = self.pinned_path
            return
        if now - self.last_activity < self.switch_after:
            return
        try:
            current_mtime = self.log_path.stat().st_mtime
        except FileNotFoundError:
            current_mtime = 0.0
        candidate = _recent_log_any(self.sessions_root, current_mtime + 0.01, self.cwd)
        if candidate and candidate != self.log_path:
            _log_debug(f"switch:mtime from={self.log_path} to={candidate}")
            self.next_path = candidate

    def _tui_resume_candidate(self) -> Path | None:
        try:
            mtime = TUI_LOG_PATH.stat().st_mtime
        except FileNotFoundError:
            return None
        if mtime <= self.tui_log_mtime:
            return None
        self.tui_log_mtime = mtime
        return _resume_log_from_tui(TUI_LOG_PATH, self.cwd)

    def _history_candidate(self) -> Path | None:
        try:
            stat = HISTORY_LOG_PATH.stat()
        except FileNotFoundError:
            return None
        if stat.st_size <= self.history_offset:
            return None
        if self.history_offset > stat.st_size:
            self.history_offset = 0
        candidate: Path | None = None
        try:
            with HISTORY_LOG_PATH.open(encoding="utf-8", errors="ignore") as handle:
                handle.seek(self.history_offset)
                for line in handle:
                    self.history_offset = handle.tell()
                    data = _parse_json(line)
                    if data is None:
                        continue
                    ts = _parse_history_ts(data.get("ts"))
                    if ts is not None and _timestamp_trustworthy(ts, self.start_time):
                        if ts < self.start_time - 1:
                            continue
                    session_id = data.get("session_id")
                    if not isinstance(session_id, str):
                        continue
                    if self.session_id and session_id == self.session_id:
                        continue
                    path = _find_log_by_session_id(self.sessions_root, session_id, self.cwd)
                    if path is None:
                        continue
                    candidate = path
                    break
        except Exception:
            return None
        if candidate is not None:
            _log_debug(f"resume:history session_id={session_id} path={candidate}")
        return candidate


def wait_for_log(
    session_dir: Path,
    start_time: float,
    stop_event: threading.Event,
    allow_external_switch: bool,
    codex_pid: int | None = None,
    fallback_after: float = 2.0,
) -> tuple[Path | None, str | None]:
    existing = set(session_dir.glob("rollout-*.jsonl")) if session_dir.exists() else set()
    started = time.time()
    fallback_checked = 0.0
    pid_checked = 0.0
    sessions_root = Path.home() / ".codex" / "sessions"
    cwd = Path.cwd()
    tui_log_mtime = 0.0
    while not stop_event.is_set():
        if codex_pid is not None and _PID_LOG_TIMEOUT_SECS > 0:
            now = time.time()
            if now - started <= _PID_LOG_TIMEOUT_SECS and now - pid_checked >= 0.4:
                pid_checked = now
                path = _log_path_from_pid(codex_pid)
                if path:
                    _log_debug(f"wait_for_log:pid path={path}")
                    return path, "pid"
        if allow_external_switch:
            try:
                tui_mtime = TUI_LOG_PATH.stat().st_mtime
            except FileNotFoundError:
                tui_mtime = 0.0
            if tui_mtime > tui_log_mtime:
                tui_log_mtime = tui_mtime
                resume_path = _resume_log_from_tui(TUI_LOG_PATH, cwd)
                if resume_path:
                    _log_debug(f"wait_for_log:tui path={resume_path}")
                    return resume_path, "tui"
        if session_dir.exists():
            candidates = []
            for path in session_dir.glob("rollout-*.jsonl"):
                try:
                    mtime = path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if path in existing and not allow_external_switch:
                    continue
                if path in existing:
                    if mtime >= start_time:
                        candidates.append((mtime, path))
                elif mtime >= start_time - 1:
                    candidates.append((mtime, path))
            if candidates:
                chosen = _best_log_candidate(candidates, start_time, cwd) or max(
                    candidates, key=lambda item: item[0]
                )[1]
                _log_debug(f"wait_for_log:session_dir path={chosen}")
                return chosen, "session_dir"
        if allow_external_switch and fallback_after >= 0 and time.time() - started >= fallback_after:
            if time.time() - fallback_checked >= 0.5:
                candidate = _recent_log_any(sessions_root, start_time - 1, cwd)
                if candidate:
                    _log_debug(f"wait_for_log:recent_any path={candidate}")
                    return candidate, "recent_any"
                fallback_checked = time.time()
        time.sleep(0.2)
    return None, None


def watch_log(
    log_path: Path,
    title: TitleWriter,
    running_title: str,
    done_title: str,
    no_commit_title: str,
    stop_event: threading.Event,
    start_time: float | None,
    start_offset: int | None,
    done_state: DoneState | None,
    allow_external_switch: bool,
) -> Path | None:
    pending_user = False
    session_id = _session_id_from_log(log_path)
    history_seen = session_id is not None and _history_has_session(session_id)
    real_user_seen = history_seen
    commit_root = _git_repo_root(Path.cwd()) if no_commit_title else None
    turn_base_head: str | None = None
    pending_commit_calls: dict[str, bool] = {}
    pending_tool_calls: set[str] = set()
    turn_commit_seen = False
    last_response_activity: float | None = None
    idle_timeout = _IDLE_DONE_SECS
    idle_interval: float | None = None
    if idle_timeout > 0:
        idle_interval = min(0.5, max(0.1, idle_timeout / 2))
    switch_state = SwitchState(
        log_path=log_path,
        sessions_root=Path.home() / ".codex" / "sessions",
        cwd=Path.cwd(),
        start_time=start_time or time.time(),
        allow_external_switch=allow_external_switch,
    )

    def set_done_title() -> None:
        if turn_commit_seen:
            title.set(done_title)
        elif no_commit_title and commit_root and turn_base_head is not None:
            current_head = _git_head(commit_root)
            if current_head and current_head != turn_base_head:
                title.set(done_title)
            else:
                title.set(no_commit_title)
        else:
            title.set(done_title)
        if done_state is not None:
            done_state.seen = True

    def refresh_real_user(text: str | None) -> bool:
        nonlocal real_user_seen
        if real_user_seen:
            return True
        if text is None:
            if session_id and _history_has_session(session_id, limit=200):
                real_user_seen = True
            return real_user_seen
        if _is_bootstrap_message(text):
            if session_id and _history_has_session(session_id, limit=200):
                real_user_seen = True
            return real_user_seen
        real_user_seen = True
        return True

    def note_response_activity() -> None:
        nonlocal last_response_activity
        last_response_activity = time.monotonic()

    iter_start_time = None if start_offset is not None else start_time
    for event in iter_jsonl(
        log_path,
        stop_event,
        iter_start_time,
        switch_state,
        start_offset=start_offset,
        idle_interval=idle_interval,
    ):
        if stop_event.is_set():
            break
        etype = event.get("type")
        if etype == "_idle":
            now = time.monotonic()
            if _should_idle_done(
                pending_user,
                real_user_seen,
                pending_tool_calls,
                last_response_activity,
                now,
                idle_timeout,
            ):
                pending_user = False
                last_response_activity = None
                set_done_title()
            continue
        payload = event.get("payload") or {}
        user_text = _extract_user_text(etype, payload)
        if user_text is None:
            note_response_activity()
        if etype == "event_msg":
            msg_type = payload.get("type")
            if msg_type == "user_message":
                pending_user = True
                last_response_activity = None
                pending_tool_calls.clear()
                turn_commit_seen = False
                pending_commit_calls.clear()
                if commit_root:
                    turn_base_head = _git_head(commit_root)
                if _is_resume_command(user_text):
                    switch_state.allow_external_switch = True
                if refresh_real_user(user_text):
                    title.set(running_title)
            elif msg_type in {"agent_message", "assistant_message", "turn_aborted"}:
                pending_user = False
                last_response_activity = None
                if real_user_seen:
                    set_done_title()
        elif etype == "response_item" and payload.get("type") == "message":
            role = payload.get("role")
            if role == "user":
                pending_user = True
                last_response_activity = None
                pending_tool_calls.clear()
                turn_commit_seen = False
                pending_commit_calls.clear()
                if commit_root:
                    turn_base_head = _git_head(commit_root)
                if _is_resume_command(user_text):
                    switch_state.allow_external_switch = True
                if refresh_real_user(user_text):
                    title.set(running_title)
            elif role == "assistant":
                pending_user = False
                last_response_activity = None
                if real_user_seen:
                    set_done_title()
        elif etype == "response_item":
            resp_type = payload.get("type")
            _note_tool_call(resp_type, payload, pending_tool_calls)
            if resp_type in {"reasoning", "function_call", "custom_tool_call"}:
                if pending_user and refresh_real_user(user_text):
                    title.set(running_title)
            if resp_type == "function_call":
                cmd = _extract_command(payload)
                if cmd and _command_has_git_commit(cmd):
                    call_id = payload.get("call_id")
                    if isinstance(call_id, str):
                        pending_commit_calls[call_id] = True
            elif resp_type == "function_call_output":
                call_id = payload.get("call_id")
                if isinstance(call_id, str) and pending_commit_calls.pop(call_id, None):
                    output = payload.get("output")
                    if isinstance(output, str) and _parse_exit_code(output) == 0:
                        turn_commit_seen = True
    return switch_state.next_path


def start_watcher(
    log_path: Path | None,
    session_dir: Path,
    start_time: float,
    title: TitleWriter,
    running_title: str,
    done_title: str,
    no_commit_title: str,
    stop_event: threading.Event,
    done_state: DoneState | None,
    resume_hint: bool,
    codex_pid: int | None,
) -> threading.Thread:
    def _run() -> None:
        allow_initial_resume = _FOLLOW_GLOBAL_RESUME or resume_hint
        allow_external_switch = _FOLLOW_GLOBAL_RESUME
        path = log_path
        source = "arg" if log_path else None
        if path is None:
            path, source = wait_for_log(
                session_dir,
                start_time,
                stop_event,
                allow_external_switch=allow_initial_resume,
                codex_pid=codex_pid,
            )
        if not path:
            _log_debug("watcher:no_log_found")
            return
        allow_unseen = allow_initial_resume or source in {"arg", "pid", "tui", "history"}
        while path and not stop_event.is_set():
            _log_debug(f"watcher:start path={path}")
            try:
                start_offset = path.stat().st_size
            except FileNotFoundError:
                start_offset = None
            initial_title = _initial_title_from_log(
                path,
                running_title,
                done_title,
                no_commit_title,
                allow_unseen=allow_unseen,
            )
            if initial_title is None and resume_hint:
                initial_title = _initial_title_from_recent_logs(
                    session_dir,
                    path,
                    running_title,
                    done_title,
                    no_commit_title,
                    allow_unseen=allow_unseen,
                )
            if initial_title:
                _log_debug(f"watcher:initial_title title={initial_title}")
                title.set(initial_title)
                if done_state is not None and initial_title in {done_title, no_commit_title}:
                    done_state.seen = True
            next_path = watch_log(
                path,
                title,
                running_title,
                done_title,
                no_commit_title,
                stop_event,
                start_time,
                start_offset,
                done_state,
                allow_external_switch,
            )
            if next_path and next_path != path:
                path = next_path
                allow_unseen = True
                continue
            break

    thread = threading.Thread(target=_run, name="codex-title-watch", daemon=True)
    thread.start()
    return thread


def parse_args(argv: list[str], defaults: dict[str, str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Codex with terminal tab title updates based on session logs."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(defaults["config_path"]),
        help=f"Config file path (default: {defaults['config_path']}).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the resolved title and log path without updating the terminal title.",
    )
    parser.add_argument(
        "--watch-only",
        action="store_true",
        help="Only watch logs; do not start Codex.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--follow-global-resume",
        action="store_true",
        help="Follow Codex resume signals across sessions (may sync titles across tabs).",
    )
    parser.add_argument(
        "--session-dir",
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--new-title",
        default=defaults["new_title"],
        help="Title to set on session start before any prompts.",
    )
    parser.add_argument(
        "--running-title",
        default=defaults["running_title"],
        help="Title to set while Codex is running.",
    )
    parser.add_argument(
        "--done-title",
        default=defaults["done_title"],
        help="Title to set when Codex finishes a response.",
    )
    parser.add_argument(
        "--no-commit-title",
        default=defaults["no_commit_title"],
        help="Title to set when no git commit was made during the last turn.",
    )
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="Run Codex with --dangerously-bypass-approvals-and-sandbox.",
    )
    parser.add_argument(
        "codex_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to codex after --",
    )
    args = parser.parse_args(argv)
    if args.codex_args[:1] == ["--"]:
        args.codex_args = args.codex_args[1:]
    return args


def main() -> int:
    argv = sys.argv[1:]
    defaults = _resolve_defaults(argv)
    args = parse_args(argv, defaults)
    if args.follow_global_resume:
        global _FOLLOW_GLOBAL_RESUME
        _FOLLOW_GLOBAL_RESUME = True
    if args.status:
        session_dir = args.session_dir or session_dir_for_time(time.time())
        cwd = Path.cwd()
        path, source = _status_log_path(session_dir, cwd)
        title_value = args.new_title
        if path:
            initial_title = _initial_title_from_log(
                path,
                args.running_title,
                args.done_title,
                args.no_commit_title,
                allow_unseen=True,
            )
            if initial_title:
                title_value = initial_title
        session_id = _session_id_from_log(path) if path else None
        print(f"title: {title_value}")
        if path:
            print(f"log_path: {path}")
        if source:
            print(f"source: {source}")
        if session_id:
            print(f"session_id: {session_id}")
        return 0

    title = TitleWriter()
    title.set(args.new_title)

    stop_event = threading.Event()
    done_state = DoneState()

    def _signal_handler(_signum: int, _frame: object) -> None:
        stop_event.set()
        if args.no_commit_title:
            title.set(args.no_commit_title)
        else:
            title.set(args.done_title)
        done_state.seen = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    session_dir = args.session_dir or session_dir_for_time(time.time())

    if args.watch_only:
        watcher = start_watcher(
            args.log,
            session_dir,
            time.time(),
            title,
            args.running_title,
            args.done_title,
            args.no_commit_title,
            stop_event,
            done_state,
            resume_hint=("--resume" in args.codex_args or "--last" in args.codex_args),
            codex_pid=None,
        )
        try:
            while watcher.is_alive():
                time.sleep(0.2)
        finally:
            stop_event.set()
            if not done_state.seen:
                if args.no_commit_title:
                    title.set(args.no_commit_title)
                else:
                    title.set(args.done_title)
        return 0

    codex_args = list(args.codex_args)
    if args.yolo and "--dangerously-bypass-approvals-and-sandbox" not in codex_args:
        codex_args = ["--dangerously-bypass-approvals-and-sandbox", *codex_args]
    cmd = ["codex"] + codex_args
    proc = subprocess.Popen(cmd)
    watcher = start_watcher(
        args.log,
        session_dir,
        time.time(),
        title,
        args.running_title,
        args.done_title,
        args.no_commit_title,
        stop_event,
        done_state,
        resume_hint=("--resume" in args.codex_args or "--last" in args.codex_args),
        codex_pid=proc.pid,
    )
    try:
        return proc.wait()
    finally:
        stop_event.set()
        if not done_state.seen:
            if args.no_commit_title:
                title.set(args.no_commit_title)
            else:
                title.set(args.done_title)


if __name__ == "__main__":
    raise SystemExit(main())
