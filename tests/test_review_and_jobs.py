"""Unit tests for Phase 5 (Review Package & Quality Traps) and Phase 6 (Jobs & Checkpoints)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from artcraft_plugin import cli, jobs, review, tools


def create_textured_image(width: int, height: int, noise_std: float = 30.0) -> Image.Image:
    """Create an authentic textured photographic fixture using numpy noise."""
    base = np.full((height, width), 128.0, dtype=np.float64)
    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, noise_std, (height, width))
    arr = np.clip(base + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L").convert("RGB")


class TestReviewPackageAndQualityTraps(unittest.TestCase):
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
        self.assertGreaterEqual(max(crop_metrics["variance_drop_pct"], crop_metrics["laplacian_drop_pct"]), 80.0)

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
        """CLI subcommand `hermes artcraft review` executes and exits cleanly."""
        src_p = self.root / "cli_src.png"
        out_p = self.root / "cli_out.png"
        img = create_textured_image(100, 100)
        img.save(src_p)
        img.save(out_p)

        # No-op edit should exit 1
        exit_code = cli.main(["review", str(src_p), str(out_p), "--working-dir", str(self.work_dir)])
        self.assertEqual(exit_code, 1)


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
        jobs.save_checkpoint("job_recover", "tone_adjust", cp1_p, verified=True, workspace_dir=self.workspace)

        # Step 2: Verified checkpoint
        cp2_p = Path(self.temp_dir.name) / "step2.png"
        Image.new("RGB", (100, 100), color=(70, 70, 70)).save(cp2_p)
        jobs.save_checkpoint("job_recover", "spot_heal", cp2_p, verified=True, workspace_dir=self.workspace)

        # Step 3: Interrupted / unverified work
        cp3_p = Path(self.temp_dir.name) / "step3_crashed.png"
        Image.new("RGB", (100, 100), color=(80, 80, 80)).save(cp3_p)
        jobs.save_checkpoint("job_recover", "interrupted_step", cp3_p, verified=False, workspace_dir=self.workspace)

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
        err = jobs.record_export_artifact("job_export", "print_final", art_p, verified=False, workspace_dir=self.workspace)
        self.assertFalse(err["ok"])

        # Records verified artifact
        rec = jobs.record_export_artifact("job_export", "print_final", art_p, verified=True, workspace_dir=self.workspace)
        self.assertTrue(rec["ok"])
        self.assertTrue(rec["artifact"]["verified"])
        self.assertTrue(Path(rec["artifact"]["path"]).is_file())

    def test_delivery_receipt_duplicate_prevention_and_reconciliation(self) -> None:
        """Full delivery lifecycle: prevents duplicate deliveries and reconciles uncertain state."""
        jobs.init_job("job_delivery", workspace_dir=self.workspace)
        art_p = Path(self.temp_dir.name) / "deliver_ready.png"
        Image.new("RGB", (100, 100), color=(130, 130, 130)).save(art_p)
        jobs.record_export_artifact("job_delivery", "art_1", art_p, verified=True, workspace_dir=self.workspace)

        dest_file = Path(self.temp_dir.name) / "customer_inbox" / "delivered_photo.png"

        # 1. Successful delivery
        deliv1 = jobs.record_delivery("job_delivery", str(dest_file), "art_1", status="delivered", workspace_dir=self.workspace)
        self.assertTrue(deliv1["ok"])
        self.assertTrue(dest_file.is_file())

        # 2. Duplicate delivery attempt of identical hash to same destination is prevented
        deliv_dup = jobs.record_delivery("job_delivery", str(dest_file), "art_1", status="delivered", workspace_dir=self.workspace)
        self.assertTrue(deliv_dup["ok"])
        self.assertTrue(deliv_dup.get("duplicate_prevented"))

        # 3. Uncertain delivery
        dest_uncertain = Path(self.temp_dir.name) / "customer_inbox" / "uncertain_photo.png"
        deliv_unc = jobs.record_delivery("job_delivery", str(dest_uncertain), "art_1", status="uncertain", workspace_dir=self.workspace)
        self.assertTrue(deliv_unc["ok"])
        self.assertEqual(deliv_unc["receipt"]["status"], "uncertain")

        # 4. Attempting to deliver again before reconciliation is refused
        retry_blocked = jobs.record_delivery("job_delivery", str(dest_uncertain), "art_1", status="delivered", workspace_dir=self.workspace)
        self.assertFalse(retry_blocked["ok"])
        self.assertTrue(retry_blocked["requires_reconciliation"])

        # 5. Reconcile uncertain delivery: since file doesn't exist yet, reconciles to 'failed'
        recon = jobs.reconcile_delivery("job_delivery", str(dest_uncertain), workspace_dir=self.workspace)
        self.assertTrue(recon["ok"])
        self.assertEqual(recon["reconciled_status"], "failed")

        # 6. Now that uncertain state is reconciled, delivery retry proceeds safely
        deliv_retry = jobs.record_delivery("job_delivery", str(dest_uncertain), "art_1", status="delivered", workspace_dir=self.workspace)
        self.assertTrue(deliv_retry["ok"])
        self.assertTrue(dest_uncertain.is_file())

    def test_cli_job_commands(self) -> None:
        """CLI `hermes artcraft job` subcommands execute end-to-end."""
        src_p = Path(self.temp_dir.name) / "cli_job_src.png"
        Image.new("RGB", (100, 100), color=(140, 140, 140)).save(src_p)

        # init
        code = cli.main(["job", "init", "cli_job_1", "--source", str(src_p), "--workspace", str(self.workspace)])
        self.assertEqual(code, 0)

        # checkpoint
        code = cli.main(["job", "checkpoint", "cli_job_1", "--stage", "step1", "--file", str(src_p), "--workspace", str(self.workspace)])
        self.assertEqual(code, 0)

        # resume
        code = cli.main(["job", "resume", "cli_job_1", "--workspace", str(self.workspace)])
        self.assertEqual(code, 0)

        # export
        code = cli.main(["job", "export", "cli_job_1", "--artifact-id", "art_cli", "--file", str(src_p), "--workspace", str(self.workspace)])
        self.assertEqual(code, 0)

        # deliver
        dest = Path(self.temp_dir.name) / "cli_delivery.png"
        code = cli.main(["job", "deliver", "cli_job_1", "--artifact-id", "art_cli", "--destination", str(dest), "--status", "delivered", "--workspace", str(self.workspace)])
        self.assertEqual(code, 0)
        self.assertTrue(dest.is_file())

        # status
        code = cli.main(["job", "status", "cli_job_1", "--workspace", str(self.workspace)])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
