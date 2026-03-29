"""Utilities for persisted translation run logs and parsed worker state."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

_WORKER_ID_PATTERNS = (
    re.compile(r"\[id:\s*([^\]]+)\]"),
    re.compile(r"^\[([^\]]+)\]"),
)

_CHUNK_PATTERN = re.compile(r"(chunk_\d+|global_proofreading)")

_STAGE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"ЭТАП 1"), "discovery"),
    (re.compile(r"ЭТАП 2"), "translation"),
    (re.compile(r"ЭТАП 3\.5"), "global_proofreading"),
    (re.compile(r"ЭТАП 3"), "proofreading"),
    (re.compile(r"Сборка итогового файла"), "assembly"),
    (re.compile(r"Процесс завершен"), "finished"),
)

_RUNNING_PATTERN = re.compile(r"Запущен воркер \[id:\s*([^\]]+)\] для: ([^\s]+)")
_SUCCESS_PATTERN = re.compile(r"Воркер \[id:\s*([^\]]+)\] для ([^\s]+) успешно завершен")
_FAILED_PATTERN = re.compile(r"Воркер \[id:\s*([^\]]+)\] для ([^\s]+) завершился с ошибкой")
_TIMEOUT_PATTERN = re.compile(r"Воркер \[id:\s*([^\]]+)\] .*превысил лимит времени")
_CRASH_PATTERN = re.compile(r"ОШИБКА.*воркера \[id:\s*([^\]]+)\] для ([^\s:]+)")


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    return cleaned.strip("-") or "run"


def extract_worker_id_from_message(message: str) -> str | None:
    for pattern in _WORKER_ID_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group(1)
    return None


def extract_chunk_label(message: str) -> str | None:
    match = _CHUNK_PATTERN.search(message)
    return match.group(1) if match else None


def detect_stage(message: str, current_stage: str | None = None) -> str | None:
    for pattern, stage in _STAGE_PATTERNS:
        if pattern.search(message):
            return stage
    return current_stage


def parse_worker_event(message: str, current_stage: str | None) -> dict[str, str] | None:
    for pattern, status in (
        (_RUNNING_PATTERN, "running"),
        (_SUCCESS_PATTERN, "success"),
        (_FAILED_PATTERN, "failed"),
        (_CRASH_PATTERN, "crashed"),
    ):
        match = pattern.search(message)
        if match:
            worker_id, chunk_label = match.groups()
            return {
                "worker_id": worker_id,
                "chunk_label": chunk_label,
                "stage": current_stage or "unknown",
                "status": status,
            }

    timeout_match = _TIMEOUT_PATTERN.search(message)
    if timeout_match:
        worker_id = timeout_match.group(1)
        return {
            "worker_id": worker_id,
            "chunk_label": extract_chunk_label(message) or "unknown",
            "stage": current_stage or "unknown",
            "status": "timeout",
        }

    return None


def create_run_artifacts(
    logs_dir: Path,
    *,
    volume_name: str,
    chapter_name: str,
    debug_mode: bool,
) -> dict[str, str]:
    timestamp = datetime.now().astimezone()
    run_id = f"{timestamp.strftime('%Y%m%dT%H%M%S')}_{safe_slug(chapter_name)}_{uuid4().hex[:6]}"
    run_dir = logs_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "volume_name": volume_name,
        "chapter_name": chapter_name,
        "debug_mode": debug_mode,
        "started_at": timestamp.isoformat(),
        "status": "running",
        "current_stage": "startup",
        "run_dir": str(run_dir),
    }
    manifest_path = run_dir / "run.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (logs_dir / "latest_run.json").write_text(
        json.dumps({"run_id": run_id, "run_dir": str(run_dir)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "manifest_path": str(manifest_path),
        "system_log_path": str(run_dir / "system_output.log"),
        "input_log_path": str(run_dir / "workers_input.log"),
        "output_log_path": str(run_dir / "workers_output.log"),
    }


def update_run_manifest(manifest_path: str | Path, **updates: object) -> None:
    path = Path(manifest_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.update(updates)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def discover_run_manifests(
    series_root: Path,
    *,
    volume_name: str | None = None,
    chapter_name: str | None = None,
) -> list[dict]:
    manifests: list[dict] = []
    for volume_dir in sorted(p for p in series_root.iterdir() if p.is_dir()):
        if volume_name and volume_dir.name != volume_name:
            continue
        runs_dir = volume_dir / ".state" / "logs" / "runs"
        if not runs_dir.is_dir():
            continue
        for manifest_path in sorted(runs_dir.glob("*/run.json"), reverse=True):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if chapter_name and manifest.get("chapter_name") != chapter_name:
                continue
            manifest["manifest_path"] = str(manifest_path)
            manifests.append(manifest)
    manifests.sort(key=lambda item: str(item.get("started_at", "")), reverse=True)
    return manifests


def load_run_records(run_dir: str | Path) -> list[dict]:
    run_dir = Path(run_dir)
    records: list[dict] = []
    for stream, filename in (
        ("system", "system_output.log"),
        ("worker_input", "workers_input.log"),
        ("worker_output", "workers_output.log"),
    ):
        file_path = run_dir / filename
        if not file_path.is_file():
            continue
        for line in file_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record["stream"] = stream
            record["worker_id"] = extract_worker_id_from_message(str(record.get("message", "")))
            records.append(record)
    records.sort(key=lambda item: str(item.get("timestamp", "")))

    current_stage = "startup"
    for record in records:
        current_stage = detect_stage(str(record.get("message", "")), current_stage) or current_stage
        record["stage"] = current_stage
    return records


def build_worker_status_rows(records: list[dict]) -> list[dict[str, str]]:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    current_stage = "startup"
    for record in records:
        current_stage = detect_stage(str(record.get("message", "")), current_stage) or current_stage
        event = parse_worker_event(str(record.get("message", "")), current_stage)
        if event is None:
            continue
        key = (event["stage"], event["worker_id"])
        rows[key] = {
            "stage": event["stage"],
            "worker_id": event["worker_id"],
            "chunk_label": event["chunk_label"],
            "status": event["status"],
            "timestamp": str(record.get("timestamp", "")),
        }
    return sorted(
        rows.values(),
        key=lambda row: (row["stage"], row["chunk_label"], row["worker_id"]),
    )


def format_record_line(record: dict) -> str:
    timestamp = str(record.get("timestamp", ""))
    time_part = timestamp[11:19] if len(timestamp) >= 19 else timestamp
    stream = str(record.get("stream") or record.get("name") or "log")
    level = str(record.get("level") or "INFO")
    message = str(record.get("message") or "")
    return f"{time_part} [{stream}:{level}] {message}"
