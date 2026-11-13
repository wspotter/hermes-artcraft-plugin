"""Hermes Agent plugin entrypoint for ArtCraft apps."""

from __future__ import annotations

from typing import Any

from artcraft_plugin import cli, schemas, tools


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

    if hasattr(ctx, "register_cli_command"):
        ctx.register_cli_command(
            "artcraft",
            cli.register_cli,
            description="Inspect ArtCraft CLIs and verify edited images",
        )
