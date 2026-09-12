"""AI slideshow assets, explicit generation, and original publishing operations."""

from __future__ import annotations

from dataclasses import replace

from museoncli.domains import _ai_slideshow_asset as asset_commands
from museoncli.domains import _ai_slideshow_generation as generation_commands
from museoncli.domains import _ai_slideshow_publish as publish_commands
from museoncli.domains import _ai_slideshow_publish_account as publish_account_commands
from museoncli.domains._model import CommandSpec


def specs() -> list[CommandSpec]:
    return [
        *(replace(spec, resource="asset") for spec in asset_commands.specs()),
        *(replace(spec, resource="generation") for spec in generation_commands.specs()),
        *(replace(spec, resource="publish") for spec in publish_commands.specs()),
        *(replace(spec, resource="publish") for spec in publish_account_commands.specs()),
    ]


EXECUTORS = {
    **asset_commands.EXECUTORS,
    **generation_commands.EXECUTORS,
    **publish_commands.EXECUTORS,
    **publish_account_commands.EXECUTORS,
}
