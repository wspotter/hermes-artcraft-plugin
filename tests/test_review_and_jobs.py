"""Tests for edit review checks, job workspaces, checkpoints, and deliveries."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from artcraft_plugin import cli, jobs, review


def create_textured_image(width: int, height: int, noise_std: float = 30.0) -> Image.Image:
    """Create an authentic textured photographic fixture using numpy noise."""
    base = np.full((height, width), 128.0, dtype=np.float64)
    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, noise_std, (height, width))
    arr = np.clip(base + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L").convert("RGB")


class TestReviewPackage(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.work_dir = self.root / "work"
        self.work_dir.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_clean_valid_edit_passes_review(self) -> None:
        """Legitimate edit with authentic grain and matching framing passes review."""
        src_p = self.root / "source.png"
        out_p = self.root / "output.png"

        img = create_textured_image(300, 300, noise_std=25.0)
        img.save(src_p)

        # Modify region [50, 50, 40, 40] with synthesized texture (authentic grain)
        out_img = img.copy()
        rng = np.random.default_rng(99)
        patch = np.clip(128.0 + rng.normal(0.0, 24.0, (40, 40)), 0, 255).astype(np.uint8)
        out_img.paste(Image.fromarray(patch, mode="L").convert("RGB"), (50, 50))
        out_img.save(out_p)

        res = review.build_review_package(
            source_path=src_p,
            output_path=out_p,
            region=[50, 50, 40, 40],
            working_dir=self.work_dir,
            preserve_framing=True,
        )

        self.assertTrue(res["ok"])
        self.assertTrue(res["passed"])
        self.assertEqual(len(res["flags"]), 0)
        self.assertEqual(res["retry_tracking"]["suggested_action"], "approve")

        # Verify previews and crops were generated
        self.assertTrue(Path(res["previews"]["source_preview_path"]).is_file())
        self.assertTrue(Path(res["previews"]["output_preview_path"]).is_file())
        self.assertEqual(len(res["crops"]), 1)
        self.assertTrue(Path(res["crops"][0]["source_crop_path"]).is_file())
        self.assertTrue(Path(res["crops"][0]["output_crop_path"]).is_file())
        self.assertGreater(res["crops"][0]["changed_pixels"], 0)

    def test_catches_untouched_scratch_no_op(self) -> None:
        """Catches 0 changed pixels in region or globally (no-op / untouched scratch)."""
        src_p = self.root / "scratch_source.png"
        out_p = self.root / "scratch_output.png"

        img = create_textured_image(200, 200, noise_std=20.0)
        img.save(src_p)
        img.save(out_p)  # identical copy

        res = review.build_review_package(
            source_path=src_p,
            output_path=out_p,
            region=[60, 60, 30, 30],
            working_dir=self.work_dir,
        )

        self.assertTrue(res["ok"])
        self.assertFalse(res["passed"])
        flag_ids = [f["id"] for f in res["flags"]]
        self.assertIn("untouched_scratch", flag_ids)
        self.assertIn("Review rejected", res["summary"])

    def test_catches_unwanted_crop_and_aspect_shift(self) -> None:
        """Catches unauthorized aspect ratio / framing shifts."""
        src_p = self.root / "photo_4x3.png"
        out_p = self.root / "photo_square.png"

        # Source is 400x300 (4:3)
        img_src = create_textured_image(400, 300)
        img_src.save(src_p)

        # Output cropped to 300x300 (1:1 square) without authorization
        img_out = img_src.crop((50, 0, 350, 300))
        img_out.save(out_p)

        res = review.build_review_package(
            source_path=src_p,
            output_path=out_p,
            preserve_framing=True,
            working_dir=self.work_dir,
        )

        self.assertTrue(res["ok"])
        self.assertFalse(res["passed"])
        flag_ids = [f["id"] for f in res["flags"]]
        self.assertIn("unwanted_crop", flag_ids)

    def test_catches_expected_aspect_violation(self) -> None:
        """Catches when output does not match an explicit expected_aspect."""
        src_p = self.root / "aspect_src.png"
        out_p = self.root / "aspect_out.png"

        img_src = create_textured_image(400, 300)
        img_src.save(src_p)
        img_src.save(out_p)

        # We request expected_aspect "1:1" but output is 4:3
        res = review.build_review_package(
            source_path=src_p,
            output_path=out_p,
            expected_aspect="1:1",
            working_dir=self.work_dir,
        )

        self.assertTrue(res["ok"])
        self.assertFalse(res["passed"])
        flag_ids = [f["id"] for f in res["flags"]]
        self.assertIn("unwanted_crop", flag_ids)

    def test_catches_smeared_repair_variance_collapse(self) -> None:
        """Catches when repaired region collapses in variance/texture (>80% drop)."""
        src_p = self.root / "textured_src.png"
        out_p = self.root / "smeared_out.png"

        # Highly textured photo
        img = create_textured_image(300, 300, noise_std=35.0)
        img.save(src_p)

        # Repair region [80, 80, 60, 60] with flat smeared blur / uniform value
        out_img = img.copy()
        smeared_patch = Image.new("RGB", (60, 60), color=(145, 145, 145))
        out_img.paste(smeared_patch, (80, 80))
        out_img.save(out_p)

        res = review.build_review_package(
            source_path=src_p,
            output_path=out_p,
            region=[80, 80, 60, 60],
            working_dir=self.work_dir,
        )

        self.assertTrue(res["ok"])
        self.assertFalse(res["passed"])
        flag_ids = [f["id"] for f in res["flags"]]
        self.assertIn("smeared_repair", flag_ids)

        # Verify variance collapse metric exceeded 80%
        crop_metrics = res["crops"][0]["texture_metrics"]
        peak_drop = max(
            crop_metrics["variance_drop_pct"],
            crop_metrics["laplacian_drop_pct"],
        )
        self.assertGreaterEqual(peak_drop, 80.0)

    def test_bounded_retry_tracking(self) -> None:
        """Retry tracking enforces bounded retries and suggested escalation."""
        src_p = self.root / "retry_src.png"
        out_p = self.root / "retry_out.png"
        img = create_textured_image(150, 150)
        img.save(src_p)
        img.save(out_p)

        # Retry 1 of 3 (failed because no-op)
        res1 = review.build_review_package(
            source_path=src_p,
            output_path=out_p,
            retry_count=1,
            max_retries=3,
            last_checkpoint_path="/checkpoints/cp_1.png",
            working_dir=self.work_dir,
        )
        self.assertFalse(res1["passed"])
        self.assertTrue(res1["retry_tracking"]["can_retry"])
        self.assertFalse(res1["retry_tracking"]["retries_exhausted"])
        self.assertEqual(res1["retry_tracking"]["suggested_action"], "retry_from_checkpoint")
        self.assertEqual(res1["retry_tracking"]["last_checkpoint_path"], "/checkpoints/cp_1.png")

        # Retry 3 of 3 (retries exhausted)
        res3 = review.build_review_package(
            source_path=src_p,
            output_path=out_p,
            retry_count=3,
            max_retries=3,
            working_dir=self.work_dir,
        )
        self.assertFalse(res3["passed"])
        self.assertFalse(res3["retry_tracking"]["can_retry"])
        self.assertTrue(res3["retry_tracking"]["retries_exhausted"])
        self.assertEqual(res3["retry_tracking"]["suggested_action"], "escalate_to_operator")

    def test_cli_review_command(self) -> None:
        """CLI `review` subcommand rejects a no-op edit with exit code 1."""
        src_p = self.root / "cli_src.png"
        out_p = self.root / "cli_out.png"
        img = create_textured_image(100, 100)
        img.save(src_p)
        img.save(out_p)

        # No-op edit should exit 1
        exit_code = cli.main(
            ["review", str(src_p), str(out_p), "--working-dir", str(self.work_dir)]
        )
        self.assertEqual(exit_code, 1)

    def test_auto_detects_rgb_change_when_alpha_is_zero(self) -> None:
        """Auto-crop detection finds RGB edits even when RGBA alpha channel is all zero."""
        src_p = self.root / "zero_alpha_src.png"
        out_p = self.root / "zero_alpha_out.png"

        src_img = Image.new("RGBA", (60, 60), color=(10, 20, 30, 0))
        src_img.save(src_p)
        out_img = src_img.copy()
        out_img.putpixel((25, 25), (200, 10, 30, 0))
        out_img.save(out_p)

        res = review.build_review_package(
            source_path=src_p,
            output_path=out_p,
            working_dir=self.work_dir,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["crops"]), 1)
        self.assertEqual(res["crops"][0]["region"], [25, 25, 1, 1])


class TestJobWorkspaceCheckpointsAndDelivery(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name) / "jobs"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_job_initialization_structure(self) -> None:
        """init_job creates source/, work/, previews/, exports/, and job.json."""
        src_p = Path(self.temp_dir.name) / "master.png"
        Image.new("RGB", (200, 200), color=(100, 150, 200)).save(src_p)

        job = jobs.init_job("job_alpha", source_path=src_p, workspace_dir=self.workspace)
        job_dir = jobs.get_job_dir("job_alpha", self.workspace)

        self.assertEqual(job["job_id"], "job_alpha")
        self.assertTrue((job_dir / "job.json").is_file())
        self.assertTrue((job_dir / "source").is_dir())
        self.assertTrue((job_dir / "work").is_dir())
        self.assertTrue((job_dir / "previews").is_dir())
        self.assertTrue((job_dir / "exports").is_dir())
        self.assertTrue(Path(job["source"]["job_source_path"]).is_file())

    def test_checkpoint_saving_and_interruption_recovery(self) -> None:
        """resume_job recovers cleanly from the last verified checkpoint."""
        src_p = Path(self.temp_dir.name) / "orig.png"
        Image.new("RGB", (100, 100), color=(50, 50, 50)).save(src_p)
        jobs.init_job("job_recover", source_path=src_p, workspace_dir=self.workspace)

        # Step 1: Verified checkpoint
        cp1_p = Path(self.temp_dir.name) / "step1.png"
        Image.new("RGB", (100, 100), color=(60, 60, 60)).save(cp1_p)
        jobs.save_checkpoint(
            "job_recover", "tone_adjust", cp1_p, verified=True, workspace_dir=self.workspace
        )

        # Step 2: Verified checkpoint
        cp2_p = Path(self.temp_dir.name) / "step2.png"
        Image.new("RGB", (100, 100), color=(70, 70, 70)).save(cp2_p)
        jobs.save_checkpoint(
            "job_recover", "spot_heal", cp2_p, verified=True, workspace_dir=self.workspace
        )

        # Step 3: Interrupted / unverified work
        cp3_p = Path(self.temp_dir.name) / "step3_crashed.png"
        Image.new("RGB", (100, 100), color=(80, 80, 80)).save(cp3_p)
        jobs.save_checkpoint(
            "job_recover", "interrupted_step", cp3_p, verified=False, workspace_dir=self.workspace
        )

        # Resume job: must recover to Step 2 (last verified checkpoint!)
        res = jobs.resume_job("job_recover", workspace_dir=self.workspace)
        self.assertTrue(res["ok"])
        self.assertTrue(res["resumed"])
        self.assertEqual(res["status"], "resumed_from_checkpoint")
        self.assertEqual(res["stage"], "spot_heal")
        self.assertEqual(res["checkpoint_id"], "cp_2_spot_heal")
        self.assertTrue(Path(res["path"]).is_file())

    def test_resume_from_source_when_no_checkpoints(self) -> None:
        """If no checkpoints exist, resume_job falls back to initial source photo."""
        src_p = Path(self.temp_dir.name) / "source_only.png"
        Image.new("RGB", (100, 100), color=(90, 90, 90)).save(src_p)
        jobs.init_job("job_fresh", source_path=src_p, workspace_dir=self.workspace)

        res = jobs.resume_job("job_fresh", workspace_dir=self.workspace)
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "resumed_from_source")
        self.assertEqual(res["stage"], "source")
        self.assertIsNone(res["checkpoint_id"])

    def test_verified_export_artifacts(self) -> None:
        """record_export_artifact enforces verification and stores artifact in exports/."""
        jobs.init_job("job_export", workspace_dir=self.workspace)
        art_p = Path(self.temp_dir.name) / "print_ready.png"
        Image.new("RGB", (300, 300), color=(120, 120, 120)).save(art_p)

        # Rejects unverified artifact
        err = jobs.record_export_artifact(
            "job_export", "print_final", art_p, verified=False, workspace_dir=self.workspace
        )
        self.assertFalse(err["ok"])

        # Records verified artifact
        rec = jobs.record_export_artifact(
            "job_export", "print_final", art_p, verified=True, workspace_dir=self.workspace
        )
        self.assertTrue(rec["ok"])
        self.assertTrue(rec["artifact"]["verified"])
        self.assertTrue(Path(rec["artifact"]["path"]).is_file())

    def test_delivery_receipt_duplicate_prevention_and_reconciliation(self) -> None:
        """Full delivery lifecycle prevents duplicates and reconciles uncertain state."""
        jobs.init_job("job_delivery", workspace_dir=self.workspace)
        art_p = Path(self.temp_dir.name) / "deliver_ready.png"
        Image.new("RGB", (100, 100), color=(130, 130, 130)).save(art_p)
        jobs.record_export_artifact(
            "job_delivery", "art_1", art_p, verified=True, workspace_dir=self.workspace
        )

        dest_file = Path(self.temp_dir.name) / "outbox" / "delivered_photo.png"

        # 1. Successful delivery
        deliv1 = jobs.record_delivery(
            "job_delivery",
            str(dest_file),
            "art_1",
            status="delivered",
            workspace_dir=self.workspace,
        )
        self.assertTrue(deliv1["ok"])
        self.assertTrue(dest_file.is_file())

        # 2. Duplicate delivery attempt of identical hash to same destination is prevented
        deliv_dup = jobs.record_delivery(
            "job_delivery",
            str(dest_file),
            "art_1",
            status="delivered",
            workspace_dir=self.workspace,
        )
        self.assertTrue(deliv_dup["ok"])
        self.assertTrue(deliv_dup.get("duplicate_prevented"))

        # 3. Uncertain delivery
        dest_uncertain = Path(self.temp_dir.name) / "outbox" / "uncertain_photo.png"
        deliv_unc = jobs.record_delivery(
            "job_delivery",
            str(dest_uncertain),
            "art_1",
            status="uncertain",
            workspace_dir=self.workspace,
        )
        self.assertTrue(deliv_unc["ok"])
        self.assertEqual(deliv_unc["receipt"]["status"], "uncertain")

        # 4. Attempting to deliver again before reconciliation is refused
        retry_blocked = jobs.record_delivery(
            "job_delivery",
            str(dest_uncertain),
            "art_1",
            status="delivered",
            workspace_dir=self.workspace,
        )
        self.assertFalse(retry_blocked["ok"])
        self.assertTrue(retry_blocked["requires_reconciliation"])

        # 5. Reconcile uncertain delivery: since file doesn't exist yet, reconciles to 'failed'
        recon = jobs.reconcile_delivery(
            "job_delivery", str(dest_uncertain), workspace_dir=self.workspace
        )
        self.assertTrue(recon["ok"])
        self.assertEqual(recon["reconciled_status"], "failed")

        # 6. Now that uncertain state is reconciled, delivery retry proceeds safely
        deliv_retry = jobs.record_delivery(
            "job_delivery",
            str(dest_uncertain),
            "art_1",
            status="delivered",
            workspace_dir=self.workspace,
        )
        self.assertTrue(deliv_retry["ok"])
        self.assertTrue(dest_uncertain.is_file())

    def test_cli_job_commands(self) -> None:
        """CLI `job` subcommands execute end-to-end."""
        src_p = Path(self.temp_dir.name) / "cli_job_src.png"
        Image.new("RGB", (100, 100), color=(140, 140, 140)).save(src_p)

        # init
        code = cli.main(
            ["job", "init", "cli_job_1", "--source", str(src_p), "--workspace", str(self.workspace)]
        )
        self.assertEqual(code, 0)

        # checkpoint
        code = cli.main(
            [
                "job",
                "checkpoint",
                "cli_job_1",
                "--stage",
                "step1",
                "--file",
                str(src_p),
                "--workspace",
                str(self.workspace),
            ]
        )
        self.assertEqual(code, 0)

        # resume
        code = cli.main(["job", "resume", "cli_job_1", "--workspace", str(self.workspace)])
        self.assertEqual(code, 0)

        # export
        code = cli.main(
            [
                "job",
                "export",
                "cli_job_1",
                "--artifact-id",
                "art_cli",
                "--file",
                str(src_p),
                "--workspace",
                str(self.workspace),
            ]
        )
        self.assertEqual(code, 0)

        # deliver
        dest = Path(self.temp_dir.name) / "cli_delivery.png"
        code = cli.main(
            [
                "job",
                "deliver",
                "cli_job_1",
                "--artifact-id",
                "art_cli",
                "--destination",
                str(dest),
                "--status",
                "delivered",
                "--workspace",
                str(self.workspace),
            ]
        )
        self.assertEqual(code, 0)
        self.assertTrue(dest.is_file())

        # status
        code = cli.main(["job", "status", "cli_job_1", "--workspace", str(self.workspace)])
        self.assertEqual(code, 0)

    def test_delivery_protects_original_and_symlinks_and_hardlinks(self) -> None:
        """Delivery rejects destinations resolving to protected paths or existing files."""
        orig_p = Path(self.temp_dir.name) / "original_photo.png"
        Image.new("RGB", (80, 80), color=(200, 100, 50)).save(orig_p)
        from artcraft_plugin.verify import sha256_file
        orig_hash = sha256_file(orig_p)

        export_p = Path(self.temp_dir.name) / "edited_export.png"
        Image.new("RGB", (80, 80), color=(10, 20, 30)).save(export_p)

        jobs.init_job("job_protect", source_path=str(orig_p), workspace_dir=self.workspace)
        cp = jobs.save_checkpoint(
            "job_protect", "heal", str(export_p), verified=True, workspace_dir=self.workspace
        )
        cp_path = Path(cp["checkpoint"]["path"])

        # Invalid export bytes must be rejected even if verified=True
        bad_export = Path(self.temp_dir.name) / "corrupt.png"
        bad_export.write_bytes(b"not-a-valid-image")
        bad_res = jobs.record_export_artifact(
            "job_protect", "bad_art", str(bad_export), verified=True, workspace_dir=self.workspace
        )
        self.assertFalse(bad_res["ok"])

        reg = jobs.record_export_artifact(
            "job_protect", "good_art", str(export_p), verified=True, workspace_dir=self.workspace
        )
        self.assertTrue(reg["ok"])

        # 1. Direct overwrite of original
        r1 = jobs.record_delivery(
            "job_protect", str(orig_p), "good_art", status="delivered", workspace_dir=self.workspace
        )
        self.assertFalse(r1["ok"])
        self.assertEqual(sha256_file(orig_p), orig_hash)

        # 2. Symlink to original
        sym_p = Path(self.temp_dir.name) / "sym_to_orig.png"
        sym_p.symlink_to(orig_p)
        r2 = jobs.record_delivery(
            "job_protect", str(sym_p), "good_art", status="delivered", workspace_dir=self.workspace
        )
        self.assertFalse(r2["ok"])
        self.assertEqual(sha256_file(orig_p), orig_hash)

        # 3. Hard link to original
        hard_p = Path(self.temp_dir.name) / "hard_to_orig.png"
        os.link(orig_p, hard_p)
        r3 = jobs.record_delivery(
            "job_protect", str(hard_p), "good_art", status="delivered", workspace_dir=self.workspace
        )
        self.assertFalse(r3["ok"])
        self.assertEqual(sha256_file(orig_p), orig_hash)

        # 4. Protected checkpoint
        r4 = jobs.record_delivery(
            "job_protect",
            str(cp_path),
            "good_art",
            status="delivered",
            workspace_dir=self.workspace,
        )
        self.assertFalse(r4["ok"])

        # 5. Existing different destination without explicit overwrite
        other_existing = Path(self.temp_dir.name) / "existing_other.png"
        Image.new("RGB", (80, 80), color=(99, 99, 99)).save(other_existing)
        other_hash = sha256_file(other_existing)
        r5 = jobs.record_delivery(
            "job_protect",
            str(other_existing),
            "good_art",
            status="delivered",
            workspace_dir=self.workspace,
        )
        self.assertFalse(r5["ok"])
        self.assertEqual(sha256_file(other_existing), other_hash)

        # 6. Changed-after-registration artifact is rejected
        registered_path = Path(reg["artifact"]["path"])
        registered_path.write_bytes(b"tampered")
        new_dest = Path(self.temp_dir.name) / "fresh_dest.png"
        r6 = jobs.record_delivery(
            "job_protect",
            str(new_dest),
            "good_art",
            status="delivered",
            workspace_dir=self.workspace,
        )
        self.assertFalse(r6["ok"])
        self.assertFalse(new_dest.exists())

    def test_remote_uncertain_delivery_stays_uncertain_without_provenance(self) -> None:
        """Remote uncertain delivery stays uncertain when local file is absent."""
        src_p = Path(self.temp_dir.name) / "remote_src.png"
        Image.new("RGB", (80, 80), color=(40, 80, 120)).save(src_p)
        jobs.init_job("job_remote", source_path=str(src_p), workspace_dir=self.workspace)
        jobs.record_export_artifact(
            "job_remote", "art_rem", str(src_p), verified=True, workspace_dir=self.workspace
        )

        remote_dest = "remote://bucket/deliveries/out.png"
        unc = jobs.record_delivery(
            "job_remote", remote_dest, "art_rem", status="uncertain", workspace_dir=self.workspace
        )
        self.assertTrue(unc["ok"])

        # Reconcile without remote evidence/provenance must stay uncertain
        recon = jobs.reconcile_delivery("job_remote", remote_dest, workspace_dir=self.workspace)
        self.assertFalse(recon["ok"])
        self.assertEqual(recon["reconciled_status"], "uncertain")

        # Retry must remain blocked
        retry = jobs.record_delivery(
            "job_remote", remote_dest, "art_rem", status="delivered", workspace_dir=self.workspace
        )
        self.assertFalse(retry["ok"])
        self.assertTrue(retry["requires_reconciliation"])

        # Caller-supplied confirmation without provenance is also rejected for remote
        bad_conf = jobs.reconcile_delivery(
            "job_remote", remote_dest, confirmed_status="failed", workspace_dir=self.workspace
        )
        self.assertFalse(bad_conf["ok"])

        # With explicit remote provenance, reconciliation succeeds
        ok_conf = jobs.reconcile_delivery(
            "job_remote",
            remote_dest,
            confirmed_status="failed",
            provenance={
                "connector": "remote-sync",
                "rpc_id": "tx-123",
                "verified_by": "sync-client",
            },
            workspace_dir=self.workspace,
        )
        self.assertTrue(ok_conf["ok"])
        self.assertEqual(ok_conf["reconciled_status"], "failed")

    def test_concurrent_delivery_produces_single_authorized_send(self) -> None:
        """Concurrent double submission serializes via locking and prevents duplicate send."""
        import concurrent.futures

        src_p = Path(self.temp_dir.name) / "conc_src.png"
        Image.new("RGB", (60, 60), color=(70, 70, 70)).save(src_p)
        jobs.init_job("job_conc", source_path=str(src_p), workspace_dir=self.workspace)
        jobs.record_export_artifact(
            "job_conc", "art_conc", str(src_p), verified=True, workspace_dir=self.workspace
        )

        dest = Path(self.temp_dir.name) / "conc_dest.png"

        def _deliver():
            return jobs.record_delivery(
                "job_conc", str(dest), "art_conc", status="delivered", workspace_dir=self.workspace
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = [f.result() for f in [pool.submit(_deliver) for _ in range(4)]]

        new_sends = [r for r in results if r.get("ok") and not r.get("duplicate_prevented")]
        dups = [r for r in results if r.get("duplicate_prevented")]
        self.assertEqual(len(new_sends), 1)
        self.assertEqual(len(dups), 3)

    def test_path_traversal_and_unsafe_ids_rejected(self) -> None:
        """Path traversal and unsafe characters in job_id, stage, artifact_id, receipt_id fail."""
        src_p = Path(self.temp_dir.name) / "valid.png"
        Image.new("RGB", (32, 32), color=(10, 20, 30)).save(src_p)

        unsafe_values = [
            "",
            "   ",
            ".",
            "..",
            "../escape",
            "a/b",
            "a\\b",
            ".hidden",
            "..hidden",
            "bad..id",
            "has space",
            "null\x00byte",
            "tab\tid",
            "nl\nid",
        ]
        for bad_id in unsafe_values:
            with self.subTest(job_id=bad_id):
                with self.assertRaises(ValueError):
                    jobs.get_job_dir(bad_id, workspace_dir=self.workspace)
                with self.assertRaises(ValueError):
                    jobs.init_job(bad_id, workspace_dir=self.workspace)

        jobs.init_job("safe_job", source_path=src_p, workspace_dir=self.workspace)
        for bad_stage in unsafe_values:
            with self.subTest(stage=bad_stage):
                with self.assertRaises(ValueError):
                    jobs.save_checkpoint("safe_job", bad_stage, src_p, workspace_dir=self.workspace)

        for bad_art in unsafe_values:
            with self.subTest(artifact_id=bad_art):
                with self.assertRaises(ValueError):
                    jobs.record_export_artifact(
                        "safe_job", bad_art, src_p, verified=True, workspace_dir=self.workspace
                    )

        jobs.record_export_artifact(
            "safe_job", "safe_art", src_p, verified=True, workspace_dir=self.workspace
        )
        dest_p = Path(self.temp_dir.name) / "safe_dest.png"
        for bad_rcpt in unsafe_values:
            with self.subTest(receipt_id=bad_rcpt):
                with self.assertRaises(ValueError):
                    jobs.record_delivery(
                        "safe_job",
                        str(dest_p),
                        "safe_art",
                        status="pending",
                        receipt_id=bad_rcpt,
                        workspace_dir=self.workspace,
                    )
                with self.assertRaises(ValueError):
                    jobs.reconcile_delivery(
                        "safe_job",
                        str(dest_p),
                        receipt_id=bad_rcpt,
                        workspace_dir=self.workspace,
                    )

        # Symlink job_dir escaping workspace is also rejected
        outside_dir = Path(self.temp_dir.name) / "outside_escape"
        outside_dir.mkdir()
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "sym_job").symlink_to(outside_dir)
        with self.assertRaises(ValueError):
            jobs.get_job_dir("sym_job", workspace_dir=self.workspace)

        # Symlink checkpoint destination in work/ and export destination in exports/ are rejected
        safe_job_dir = jobs.get_job_dir("safe_job", workspace_dir=self.workspace)
        outside_file = outside_dir / "outside.png"
        Image.new("RGB", (32, 32), color=(1, 2, 3)).save(outside_file)
        (safe_job_dir / "work" / "cp_1_escape_valid.png").symlink_to(outside_file)
        with self.assertRaises(ValueError):
            jobs.save_checkpoint("safe_job", "escape", src_p, workspace_dir=self.workspace)

        (safe_job_dir / "exports" / "escape_art_valid.png").symlink_to(outside_file)
        with self.assertRaises(ValueError):
            jobs.record_export_artifact(
                "safe_job", "escape_art", src_p, verified=True, workspace_dir=self.workspace
            )

    def test_concurrent_save_checkpoint_preserves_all_records_and_unique_indices(self) -> None:
        """Concurrent save_checkpoint calls serialize via _job_lock and keep unique indices."""
        import concurrent.futures

        src_p = Path(self.temp_dir.name) / "cp_src.png"
        Image.new("RGB", (40, 40), color=(90, 90, 90)).save(src_p)
        jobs.init_job("job_cp_conc", source_path=src_p, workspace_dir=self.workspace)

        step_files = []
        for i in range(6):
            p = Path(self.temp_dir.name) / f"step_{i}.png"
            Image.new("RGB", (40, 40), color=(90 + i, 90, 90)).save(p)
            step_files.append(p)

        def _save(idx: int):
            return jobs.save_checkpoint(
                "job_cp_conc",
                f"stage_{idx}",
                step_files[idx],
                verified=True,
                workspace_dir=self.workspace,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = [f.result() for f in [pool.submit(_save, i) for i in range(6)]]

        self.assertTrue(all(r["ok"] for r in results))
        job = jobs.get_job("job_cp_conc", workspace_dir=self.workspace)
        checkpoints = job["checkpoints"]
        self.assertEqual(len(checkpoints), 6)
        cp_ids = [cp["checkpoint_id"] for cp in checkpoints]
        self.assertEqual(len(set(cp_ids)), 6)
        indices = sorted(int(cid.split("_")[1]) for cid in cp_ids)
        self.assertEqual(indices, [1, 2, 3, 4, 5, 6])
        for cp in checkpoints:
            self.assertTrue(Path(cp["path"]).is_file())

    def test_init_job_raises_on_corrupt_job_json_without_overwriting(self) -> None:
        """init_job fails loudly on corrupt job.json instead of overwriting with blank state."""
        job_dir = jobs.get_job_dir("job_corrupt", workspace_dir=self.workspace)
        job_dir.mkdir(parents=True, exist_ok=True)
        job_file = job_dir / "job.json"
        corrupt_payload = "{corrupt-json-not-valid"
        job_file.write_text(corrupt_payload, encoding="utf-8")

        with self.assertRaises(ValueError):
            jobs.init_job("job_corrupt", workspace_dir=self.workspace)

        self.assertEqual(job_file.read_text(encoding="utf-8"), corrupt_payload)

    def test_record_delivery_rejects_duplicate_explicit_receipt_id(self) -> None:
        """record_delivery refuses to overwrite an existing explicit receipt_id."""
        src_p = Path(self.temp_dir.name) / "rcpt_src.png"
        Image.new("RGB", (40, 40), color=(50, 60, 70)).save(src_p)
        jobs.init_job("job_rcpt_dup", source_path=src_p, workspace_dir=self.workspace)
        jobs.record_export_artifact(
            "job_rcpt_dup", "art_1", src_p, verified=True, workspace_dir=self.workspace
        )

        dest1 = Path(self.temp_dir.name) / "dest1.png"
        dest2 = Path(self.temp_dir.name) / "dest2.png"
        first = jobs.record_delivery(
            "job_rcpt_dup",
            str(dest1),
            "art_1",
            status="pending",
            receipt_id="rcpt_fixed_1",
            workspace_dir=self.workspace,
        )
        self.assertTrue(first["ok"])

        dup = jobs.record_delivery(
            "job_rcpt_dup",
            str(dest2),
            "art_1",
            status="delivered",
            receipt_id="rcpt_fixed_1",
            workspace_dir=self.workspace,
        )
        self.assertFalse(dup["ok"])
        self.assertIn("rcpt_fixed_1", dup["error"])
        self.assertIn("reconcile_delivery", dup["error"])
        self.assertFalse(dest2.exists())

        saved = jobs.get_job("job_rcpt_dup", workspace_dir=self.workspace)
        self.assertEqual(saved["delivery_receipts"]["rcpt_fixed_1"]["destination"], str(dest1))
        self.assertEqual(saved["delivery_receipts"]["rcpt_fixed_1"]["status"], "pending")

    def test_get_job_rejects_non_dict_and_delivery_refuses_dangling_symlink(self) -> None:
        """get_job rejects non-dict JSON and record_delivery refuses dangling symlink dest."""
        src_p = Path(self.temp_dir.name) / "deliv_sym_src.png"
        Image.new("RGB", (40, 40), color=(80, 90, 100)).save(src_p)
        jobs.init_job("job_sym_deliv", source_path=src_p, workspace_dir=self.workspace)
        jobs.record_export_artifact(
            "job_sym_deliv", "art_sym", src_p, verified=True, workspace_dir=self.workspace
        )

        dangling_dest = Path(self.temp_dir.name) / "dangling_dest.png"
        missing_target = Path(self.temp_dir.name) / "missing_deliv_target.png"
        os.symlink(missing_target, dangling_dest)
        res = jobs.record_delivery(
            "job_sym_deliv",
            str(dangling_dest),
            "art_sym",
            status="delivered",
            overwrite=False,
            workspace_dir=self.workspace,
        )
        self.assertFalse(res["ok"])
        self.assertTrue(res["destination_exists"])
        self.assertFalse(missing_target.exists())

        job_dir = jobs.get_job_dir("job_sym_deliv", workspace_dir=self.workspace)
        (job_dir / "job.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            jobs.get_job("job_sym_deliv", workspace_dir=self.workspace)


if __name__ == "__main__":
    unittest.main()
