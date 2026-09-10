"""ComfyUI entrypoint for H3 Prompt Compiler.

Supports both normal package loading and direct file execution used by some
custom-node loaders/test harnesses.
"""
from __future__ import annotations

try:
    from .h3_prompt_compiler.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
except ImportError:  # direct file execution without package context
    import sys
    from pathlib import Path

    plugin_root = str(Path(__file__).resolve().parent)
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)
    from h3_prompt_compiler.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
