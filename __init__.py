"""Hermes Agent plugin entrypoint for ArtCraft apps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artcraft_plugin import cli, schemas, tools


def register(ctx: Any) -> None:
    """Register ArtCraft tools and CLI subcommands with Hermes PluginManager."""
    ctx.register_tool(
        name="artcraft_status",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_STATUS,
        handler=tools.artcraft_status,
    )
    ctx.register_tool(
        name="artcraft_inspect",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_INSPECT,
        handler=tools.artcraft_inspect,
    )
    ctx.register_tool(
        name="artcraft_prepare_inspection",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_PREPARE_INSPECTION,
        handler=tools.artcraft_prepare_inspection,
    )
    ctx.register_tool(
        name="artcraft_prepare_print",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_PREPARE_PRINT,
        handler=tools.artcraft_prepare_print,
    )
    ctx.register_tool(
        name="artcraft_verify_edit",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_VERIFY_EDIT,
        handler=tools.artcraft_verify_edit,
    )
    ctx.register_tool(
        name="photocraft_run",
        toolset="artcraft",
        schema=schemas.PHOTOCRAFT_RUN,
        handler=tools.photocraft_run,
    )
    ctx.register_tool(
        name="lightcraft_run",
        toolset="artcraft",
        schema=schemas.LIGHTCRAFT_RUN,
        handler=tools.lightcraft_run,
    )

    ctx.register_tool(
        name="photocraft_spot_heal",
        toolset="artcraft",
        schema=schemas.PHOTOCRAFT_SPOT_HEAL,
        handler=tools.photocraft_spot_heal,
    )
    ctx.register_tool(
        name="artcraft_restore_step",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_RESTORE_STEP,
        handler=tools.artcraft_restore_step,
    )
    ctx.register_tool(
        name="artcraft_checkpoint",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_CHECKPOINT,
        handler=tools.artcraft_checkpoint,
    )
    ctx.register_tool(
        name="artcraft_build_review",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_BUILD_REVIEW,
        handler=tools.artcraft_build_review,
    )
    ctx.register_tool(
        name="artcraft_job",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_JOB,
        handler=tools.artcraft_job,
    )
    ctx.register_tool(
        name="artcraft_develop",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_DEVELOP,
        handler=tools.artcraft_develop,
    )
    ctx.register_tool(
        name="artcraft_audio_basic",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_AUDIO_BASIC,
        handler=tools.artcraft_audio_basic,
    )
    ctx.register_tool(
        name="artcraft_video_basic",
        toolset="artcraft",
        schema=schemas.ARTCRAFT_VIDEO_BASIC,
        handler=tools.artcraft_video_basic,
    )

    if hasattr(ctx, "register_cli_command"):
        ctx.register_cli_command(
            "artcraft",
            help="Inspect ArtCraft CLIs and verify edited images",
            setup_fn=cli.register_cli,
            description="Inspect ArtCraft CLIs and verify edited images",
        )

    if hasattr(ctx, "register_skill"):
        skills_dir = Path(__file__).resolve().parent / "skills"
        if skills_dir.is_dir():
            for child in sorted(skills_dir.iterdir()):
                skill_md = child / "SKILL.md"
                if child.is_dir() and skill_md.exists():
                    ctx.register_skill(child.name, skill_md)
