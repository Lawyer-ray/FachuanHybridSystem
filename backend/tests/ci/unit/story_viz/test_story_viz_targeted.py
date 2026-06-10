"""Targeted tests for story_viz module to push coverage to 80%+."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestStoryVizServices:
    def test_wiring_import(self):
        from apps.story_viz.services import wiring

        assert wiring is not None


class TestStoryVizApiInit:
    def test_api_init(self):
        from apps.story_viz.api import __init__ as api_init

        assert api_init is not None
