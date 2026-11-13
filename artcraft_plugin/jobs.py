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
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .verify import sha256_file


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

    job_file.write_text(json.dumps(job_data, indent=2), encoding="utf-8")
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
    job_file.write_text(json.dumps(job_data, indent=2), encoding="utf-8")


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

    job_dir = get_job_dir(job_id, workspace_dir)
    job = get_job(job_id, workspace_dir)

    src_p = Path(file_path).expanduser().resolve()
    if not src_p.is_file():
        raise FileNotFoundError(f"Export file not found: {src_p}")

    exports_dir = job_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    dest_path = exports_dir / f"{artifact_id}_{src_p.name}"
    if src_p != dest_path:
        shutil.copy2(src_p, dest_path)

    digest = sha256_file(dest_path)

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
) -> Dict[str, Any]:
    """Record delivery receipt for an export artifact.

    Guards:
      1. Prevents duplicate delivery if this hash was already delivered to destination.
      2. Refuses retry if an uncertain delivery to this destination is pending reconciliation.
    """
    valid_statuses = {"pending", "delivered", "uncertain"}
    if status not in valid_statuses:
        return {
            "ok": False,
            "error": f"Invalid delivery status '{status}'. Must be one of {valid_statuses}.",
        }

    job_dir = get_job_dir(job_id, workspace_dir)
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

    # If delivered and destination is a local path, write file
    if status == "delivered":
        try:
            dest_p = Path(destination).expanduser()
            dest_p.parent.mkdir(parents=True, exist_ok=True)
            if dest_p != art_path:
                shutil.copy2(art_path, dest_p)
        except Exception as exc:
            status = "uncertain"
            notes = f"Write error during delivery: {exc}"

    rcpt_id = receipt_id or f"rcpt_{len(receipts) + 1}_{uuid.uuid4().hex[:6]}"
    receipt_data = {
        "receipt_id": rcpt_id,
        "destination": destination,
        "artifact_id": artifact_id,
        "sha256": art_hash,
        "status": status,
        "reconciled": (status == "delivered"),
        "timestamp": iso_now(),
        "notes": notes,
    }

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
) -> Dict[str, Any]:
    """Reconcile an uncertain delivery receipt.

    Checks destination file hash (or explicit confirmation) to update status to
    'delivered' or 'failed', marking the receipt as reconciled so retries are safe.
    """
    job_dir = get_job_dir(job_id, workspace_dir)
    job = get_job(job_id, workspace_dir)

    receipts = job.get("delivery_receipts", {})
    target_rcpt: Optional[Dict[str, Any]] = None

    if receipt_id:
        target_rcpt = receipts.get(receipt_id)
    else:
        # Find latest unreconciled uncertain receipt for destination
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

    if confirmed_status in ("delivered", "failed"):
        reconciled_status = confirmed_status
        recon_notes = notes or f"Explicit reconciliation status: {confirmed_status}"
    else:
        # Check local destination file
        dest_p = Path(destination).expanduser()
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
            recon_notes = notes or "Reconciled: Destination file not found. Cleared for safe retry."

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
