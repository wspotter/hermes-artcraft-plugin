"""Deterministic job workspaces, checkpoint recovery, and delivery receipt tooling.

Provides deterministic job directory structure:
  <workspace>/<job_id>/
    source/
    work/
    previews/
    exports/
    job.json

Features:
  - Checkpoint tracking and resuming from last verified checkpoint cleanly
  - Recording verified export artifacts (artifact_id, sha256, path, verified: true)
  - Delivery receipt tracking (pending, delivered, uncertain)
  - Duplicate delivery prevention (prevents re-delivering same hash to same destination)
  - Reconciliation of uncertain delivery before retry
"""

from __future__ import annotations

import datetime
import fcntl
import json
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urlparse

from .verify import inspect_image, sha256_file


@contextmanager
def _job_lock(job_dir: Path) -> Iterator[None]:
    """Serialize mutations to a job directory via an advisory file lock."""
    job_dir.mkdir(parents=True, exist_ok=True)
    lock_path = job_dir / ".job.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _atomic_write_text(target: Path, content: str) -> None:
    """Write text atomically to target via temp file + fsync + os.replace."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _atomic_copy_verified(src: Path, dst: Path, expected_sha256: str) -> None:
    """Atomically copy src to dst via a temp file in dst.parent and verify SHA-256."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=str(dst.parent))
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
        shutil.copyfile(src, tmp_path)
        with tmp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        if sha256_file(tmp_path) != expected_sha256:
            raise IOError(f"Staged copy hash mismatch for {dst}")
        os.replace(tmp_path, dst)
        if sha256_file(dst) != expected_sha256:
            raise IOError(f"Destination hash mismatch after publish for {dst}")
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _is_remote_destination(destination: str, destination_type: Optional[str] = None) -> bool:
    """Return True for explicit remote destinations or non-file URI schemes."""
    if destination_type == "remote":
        return True
    if destination_type == "local":
        return False
    parsed = urlparse(destination.strip())
    return bool(parsed.scheme and parsed.scheme.lower() != "file" and len(parsed.scheme) > 1)


def _resolve_local_destination(destination: str) -> Path:
    """Convert a local path or file:// URI to an expanded Path."""
    raw = destination.strip()
    if raw.lower().startswith("file://"):
        raw = urlparse(raw).path
    return Path(raw).expanduser()


def _file_identity(path: Path) -> Tuple[Path, Optional[Tuple[int, int]]]:
    """Return (resolved_path, (st_dev, st_ino) or None) for symlink/hardlink detection."""
    resolved = path.resolve()
    stat_key: Optional[Tuple[int, int]] = None
    try:
        st = os.stat(resolved)
        stat_key = (st.st_dev, st.st_ino)
    except OSError:
        pass
    return resolved, stat_key


def _find_protected_collision(dest_p: Path, job: Dict[str, Any]) -> Optional[str]:
    """Check if dest_p resolves to or hardlinks any protected source/checkpoint path."""
    protected: List[Tuple[str, Path]] = []
    source = job.get("source") or {}
    if source.get("original_path"):
        protected.append(("original source", Path(source["original_path"])))
    if source.get("job_source_path"):
        protected.append(("retained job source", Path(source["job_source_path"])))
    for cp in job.get("checkpoints", []):
        if cp.get("path"):
            protected.append((f"checkpoint {cp.get('checkpoint_id', '')}".strip(), Path(cp["path"])))

    dest_resolved = dest_p.resolve()
    dest_stat: Optional[Tuple[int, int]] = None
    if dest_p.exists():
        try:
            st = os.stat(dest_p)
            dest_stat = (st.st_dev, st.st_ino)
        except OSError:
            pass

    for label, p in protected:
        p_resolved, p_stat = _file_identity(p)
        if dest_resolved == p_resolved:
            return f"Destination '{dest_p}' resolves to protected {label} '{p}'."
        if dest_stat is not None and p_stat is not None and dest_stat == p_stat:
            return f"Destination '{dest_p}' shares an inode (hard link) with protected {label} '{p}'."
    return None


def iso_now() -> str:
    """Return ISO 8601 UTC timestamp."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def get_default_workspace() -> Path:
    """Return default workspace directory for artcraft jobs."""
    env_dir = os.environ.get("ARTCRAFT_WORKSPACE_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return Path.cwd() / "artcraft_jobs"


def get_job_dir(job_id: str, workspace_dir: Optional[Union[str, Path]] = None) -> Path:
    """Return deterministic path to job directory."""
    base = Path(workspace_dir).expanduser().resolve() if workspace_dir else get_default_workspace()
    return base / str(job_id).strip()


def init_job(
    job_id: str,
    source_path: Optional[Union[str, Path]] = None,
    workspace_dir: Optional[Union[str, Path]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Initialize a deterministic job directory structure and job.json.

    Creates subdirectories: source/, work/, previews/, exports/, and writes job.json.
    """
    job_dir = get_job_dir(job_id, workspace_dir)
    source_dir = job_dir / "source"
    work_dir = job_dir / "work"
    previews_dir = job_dir / "previews"
    exports_dir = job_dir / "exports"

    for d in (source_dir, work_dir, previews_dir, exports_dir):
        d.mkdir(parents=True, exist_ok=True)

    job_file = job_dir / "job.json"
    if job_file.is_file():
        try:
            return json.loads(job_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    source_info: Optional[Dict[str, Any]] = None
    if source_path:
        src_p = Path(source_path).expanduser().resolve()
        if not src_p.is_file():
            raise FileNotFoundError(f"Source file not found: {src_p}")
        dest_src = source_dir / src_p.name
        if dest_src != src_p:
            shutil.copy2(src_p, dest_src)
        source_info = {
            "original_path": str(src_p),
            "job_source_path": str(dest_src),
            "sha256": sha256_file(dest_src),
            "filename": src_p.name,
        }

    job_data: Dict[str, Any] = {
        "job_id": str(job_id),
        "version": "1.0",
        "created_at": iso_now(),
        "updated_at": iso_now(),
        "status": "initialized",
        "workspace_path": str(job_dir),
        "source": source_info,
        "checkpoints": [],
        "current_checkpoint_id": None,
        "last_verified_checkpoint_path": None,
        "export_artifacts": {},
        "delivery_receipts": {},
        "retry_state": {
            "retry_count": 0,
            "max_retries": 3,
            "last_error": None,
        },
        "metadata": metadata or {},
    }

    _atomic_write_text(job_file, json.dumps(job_data, indent=2))
    return job_data


def get_job(job_id: str, workspace_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Load job.json for the specified job_id."""
    job_dir = get_job_dir(job_id, workspace_dir)
    job_file = job_dir / "job.json"
    if not job_file.is_file():
        raise FileNotFoundError(f"Job not found at {job_file}")
    return json.loads(job_file.read_text(encoding="utf-8"))


def _save_job(job_dir: Path, job_data: Dict[str, Any]) -> None:
    job_data["updated_at"] = iso_now()
    job_file = job_dir / "job.json"
    _atomic_write_text(job_file, json.dumps(job_data, indent=2))


def save_checkpoint(
    job_id: str,
    stage: str,
    file_path: Union[str, Path],
    *,
    verified: bool = True,
    workspace_dir: Optional[Union[str, Path]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Save an edit checkpoint into the job's work/ folder and update job.json."""
    job_dir = get_job_dir(job_id, workspace_dir)
    job = get_job(job_id, workspace_dir)

    src_p = Path(file_path).expanduser().resolve()
    if not src_p.is_file():
        raise FileNotFoundError(f"Checkpoint file not found: {src_p}")

    work_dir = job_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    idx = len(job.get("checkpoints", [])) + 1
    dest_name = f"cp_{idx}_{stage}_{src_p.name}"
    dest_path = work_dir / dest_name
    if src_p != dest_path:
        shutil.copy2(src_p, dest_path)

    digest = sha256_file(dest_path)
    checkpoint_id = f"cp_{idx}_{stage}"

    checkpoint_record = {
        "checkpoint_id": checkpoint_id,
        "stage": stage,
        "path": str(dest_path),
        "sha256": digest,
        "verified": bool(verified),
        "created_at": iso_now(),
        "metadata": metadata or {},
    }

    job.setdefault("checkpoints", []).append(checkpoint_record)
    if verified:
        job["current_checkpoint_id"] = checkpoint_id
        job["last_verified_checkpoint_path"] = str(dest_path)
        job["status"] = "checkpointed"

    _save_job(job_dir, job)
    return {
        "ok": True,
        "checkpoint": checkpoint_record,
        "job_id": job_id,
    }


def resume_job(
    job_id: str,
    workspace_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Resume an interrupted job from its last verified checkpoint (or initial source)."""
    job_dir = get_job_dir(job_id, workspace_dir)
    job = get_job(job_id, workspace_dir)

    checkpoints = job.get("checkpoints", [])
    # Search backwards for the latest verified checkpoint
    for cp in reversed(checkpoints):
        if cp.get("verified"):
            cp_path = Path(cp["path"])
            if cp_path.is_file():
                current_hash = sha256_file(cp_path)
                if current_hash == cp["sha256"]:
                    return {
                        "ok": True,
                        "resumed": True,
                        "status": "resumed_from_checkpoint",
                        "stage": cp["stage"],
                        "checkpoint_id": cp["checkpoint_id"],
                        "path": str(cp_path),
                        "sha256": current_hash,
                        "job_id": job_id,
                        "message": (
                            f"Resumed job {job_id} from last verified checkpoint '{cp['checkpoint_id']}' "
                            f"(stage: {cp['stage']})."
                        ),
                    }

    # If no verified checkpoint exists, fall back to initial source
    source = job.get("source")
    if source and source.get("job_source_path"):
        src_path = Path(source["job_source_path"])
        if src_path.is_file():
            current_hash = sha256_file(src_path)
            return {
                "ok": True,
                "resumed": True,
                "status": "resumed_from_source",
                "stage": "source",
                "checkpoint_id": None,
                "path": str(src_path),
                "sha256": current_hash,
                "job_id": job_id,
                "message": f"Resumed job {job_id} from initial source photo.",
            }

    return {
        "ok": False,
        "resumed": False,
        "error": f"No verified checkpoint or valid source file found for job {job_id}.",
    }


def record_export_artifact(
    job_id: str,
    artifact_id: str,
    file_path: Union[str, Path],
    *,
    verified: bool = True,
    workspace_dir: Optional[Union[str, Path]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record a verified export artifact in exports/ and job.json."""
    if not verified:
        return {
            "ok": False,
            "error": "Export artifacts must be verified before recording (verified=True required).",
        }

    src_p = Path(file_path).expanduser().resolve()
    if not src_p.is_file():
        raise FileNotFoundError(f"Export file not found: {src_p}")

    info = inspect_image(str(src_p))
    if not info.get("valid"):
        return {
            "ok": False,
            "error": f"invalid_export_image: {info.get('error', 'unreadable or corrupt export file')}",
        }

    job_dir = get_job_dir(job_id, workspace_dir)
    with _job_lock(job_dir):
        job = get_job(job_id, workspace_dir)
        exports_dir = job_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        digest = info["sha256"]
        dest_path = exports_dir / f"{artifact_id}_{src_p.name}"
        if src_p != dest_path:
            _atomic_copy_verified(src_p, dest_path, digest)

        artifact_record = {
            "artifact_id": str(artifact_id),
            "path": str(dest_path),
            "sha256": digest,
            "verified": True,
            "created_at": iso_now(),
            "metadata": metadata or {},
        }

        job.setdefault("export_artifacts", {})[str(artifact_id)] = artifact_record
        job["status"] = "exported"
        _save_job(job_dir, job)

    return {
        "ok": True,
        "artifact": artifact_record,
        "job_id": job_id,
    }


def record_delivery(
    job_id: str,
    destination: str,
    artifact_id: str,
    status: str = "pending",
    *,
    workspace_dir: Optional[Union[str, Path]] = None,
    receipt_id: Optional[str] = None,
    notes: Optional[str] = None,
    overwrite: bool = False,
    destination_type: Optional[str] = None,
    provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record delivery receipt for an export artifact with source protection and locking."""
    valid_statuses = {"pending", "delivered", "uncertain"}
    if status not in valid_statuses:
        return {
            "ok": False,
            "error": f"Invalid delivery status '{status}'. Must be one of {valid_statuses}.",
        }

    is_remote = _is_remote_destination(destination, destination_type)
    dest_kind = "remote" if is_remote else "local"

    job_dir = get_job_dir(job_id, workspace_dir)
    with _job_lock(job_dir):
        job = get_job(job_id, workspace_dir)

        artifacts = job.get("export_artifacts", {})
        if artifact_id not in artifacts:
            return {
                "ok": False,
                "error": f"Artifact '{artifact_id}' not found in job export artifacts.",
            }

        artifact = artifacts[artifact_id]
        art_hash = artifact["sha256"]
        art_path = Path(artifact["path"])
        receipts = job.get("delivery_receipts", {})

        # Guard 1: Duplicate delivery check
        for r in receipts.values():
            if (
                r.get("destination") == destination
                and r.get("status") == "delivered"
                and r.get("sha256") == art_hash
            ):
                return {
                    "ok": True,
                    "duplicate_prevented": True,
                    "receipt_id": r["receipt_id"],
                    "message": (
                        f"Artifact '{artifact_id}' (sha256: {art_hash[:8]}...) has already been "
                        f"delivered to '{destination}'. Duplicate delivery prevented."
                    ),
                    "receipt": r,
                }

        # Guard 2: Require reconciliation of uncertain delivery before retry
        for r in receipts.values():
            if (
                r.get("destination") == destination
                and r.get("status") == "uncertain"
                and not r.get("reconciled")
            ):
                return {
                    "ok": False,
                    "requires_reconciliation": True,
                    "error": (
                        f"Previous delivery to destination '{destination}' is in 'uncertain' state "
                        f"(receipt {r['receipt_id']}). You must reconcile before retrying."
                    ),
                    "receipt": r,
                }

        # Guard 3: Recompute export artifact hash before publishing
        if not art_path.is_file() or sha256_file(art_path) != art_hash:
            return {
                "ok": False,
                "error": f"artifact_integrity_error: '{artifact_id}' is missing or changed since registration.",
            }

        if is_remote:
            if status == "delivered" and not provenance:
                return {
                    "ok": False,
                    "requires_remote_evidence": True,
                    "error": (
                        "Remote delivery cannot be marked 'delivered' without connector provenance."
                    ),
                }
        else:
            dest_p = _resolve_local_destination(destination)
            collision = _find_protected_collision(dest_p, job)
            if collision:
                return {
                    "ok": False,
                    "protected_path_violation": True,
                    "error": f"protected_path_violation: {collision}",
                }
            if status == "delivered":
                if dest_p.exists() and not overwrite:
                    if not dest_p.is_file() or sha256_file(dest_p) != art_hash:
                        return {
                            "ok": False,
                            "destination_exists": True,
                            "error": (
                                f"destination_exists: '{dest_p}' already exists and differs from "
                                "the artifact. Pass overwrite=True to replace it."
                            ),
                        }
                try:
                    if dest_p.resolve() != art_path.resolve():
                        _atomic_copy_verified(art_path, dest_p, art_hash)
                except Exception as exc:
                    status = "uncertain"
                    notes = f"Atomic write/verify error during delivery: {exc}"

        rcpt_id = receipt_id or f"rcpt_{len(receipts) + 1}_{uuid.uuid4().hex[:6]}"
        receipt_data: Dict[str, Any] = {
            "receipt_id": rcpt_id,
            "destination": destination,
            "destination_type": dest_kind,
            "artifact_id": artifact_id,
            "sha256": art_hash,
            "status": status,
            "reconciled": (status == "delivered"),
            "timestamp": iso_now(),
            "notes": notes,
        }
        if provenance:
            receipt_data["provenance"] = provenance

        job.setdefault("delivery_receipts", {})[rcpt_id] = receipt_data
        if status == "delivered":
            job["status"] = "delivered"
        _save_job(job_dir, job)

    return {
        "ok": True,
        "receipt": receipt_data,
        "job_id": job_id,
    }


def reconcile_delivery(
    job_id: str,
    destination: str,
    *,
    receipt_id: Optional[str] = None,
    confirmed_status: Optional[str] = None,
    workspace_dir: Optional[Union[str, Path]] = None,
    notes: Optional[str] = None,
    provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Reconcile an uncertain delivery receipt without assuming missing remote files failed."""
    job_dir = get_job_dir(job_id, workspace_dir)
    with _job_lock(job_dir):
        job = get_job(job_id, workspace_dir)

        receipts = job.get("delivery_receipts", {})
        target_rcpt: Optional[Dict[str, Any]] = None

        if receipt_id:
            target_rcpt = receipts.get(receipt_id)
        else:
            for r in reversed(list(receipts.values())):
                if r.get("destination") == destination and r.get("status") == "uncertain":
                    target_rcpt = r
                    break

        if not target_rcpt:
            return {
                "ok": False,
                "error": f"No uncertain delivery receipt found for destination '{destination}'.",
            }

        expected_hash = target_rcpt["sha256"]
        is_remote = (
            target_rcpt.get("destination_type") == "remote"
            or _is_remote_destination(destination)
        )

        if is_remote:
            if confirmed_status in ("delivered", "failed") and isinstance(provenance, dict) and provenance:
                reconciled_status = confirmed_status
                recon_notes = notes or f"Remote reconciliation ({confirmed_status}) with recorded provenance."
                target_rcpt["reconciliation_provenance"] = provenance
            else:
                return {
                    "ok": False,
                    "reconciled_status": "uncertain",
                    "requires_remote_evidence": True,
                    "receipt": target_rcpt,
                    "job_id": job_id,
                    "error": (
                        "Remote destination status remains 'uncertain': explicit remote "
                        "confirmation and non-empty provenance are required."
                    ),
                }
        elif confirmed_status in ("delivered", "failed"):
            reconciled_status = confirmed_status
            recon_notes = notes or f"Explicit reconciliation status: {confirmed_status}"
            if provenance:
                target_rcpt["reconciliation_provenance"] = provenance
        else:
            dest_p = _resolve_local_destination(destination)
            if dest_p.is_file():
                actual_hash = sha256_file(dest_p)
                if actual_hash == expected_hash:
                    reconciled_status = "delivered"
                    recon_notes = notes or "Reconciled: Destination file exists and matches artifact SHA-256."
                else:
                    reconciled_status = "failed"
                    recon_notes = notes or (
                        f"Reconciled: Destination file exists but hash mismatched "
                        f"({actual_hash[:8]} vs {expected_hash[:8]}). Cleared for retry."
                    )
            else:
                reconciled_status = "failed"
                recon_notes = notes or "Reconciled: Local destination file not found. Cleared for safe retry."

        target_rcpt["status"] = reconciled_status
        target_rcpt["reconciled"] = True
        target_rcpt["reconciled_at"] = iso_now()
        target_rcpt["reconciliation_notes"] = recon_notes

        _save_job(job_dir, job)

    return {
        "ok": True,
        "receipt": target_rcpt,
        "reconciled_status": reconciled_status,
        "job_id": job_id,
        "message": f"Receipt '{target_rcpt['receipt_id']}' reconciled to '{reconciled_status}'.",
    }
