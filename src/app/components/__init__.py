# src/app/components/__init__.py
"""Composants UI réutilisables pour WaveLocalAI."""

from src.app.components.chat_message import render_chat_message, render_thinking_block
from src.app.components.metrics_display import (
    render_carbon_indicator,
    render_metrics_badge,
    render_metrics_expander,
)
from src.app.components.model_selector import render_model_selector
from src.app.components.source_expander import render_sources_expander

__all__ = [
    "render_metrics_badge",
    "render_metrics_expander",
    "render_carbon_indicator",
    "render_model_selector",
    "render_chat_message",
    "render_thinking_block",
    "render_sources_expander",
]
