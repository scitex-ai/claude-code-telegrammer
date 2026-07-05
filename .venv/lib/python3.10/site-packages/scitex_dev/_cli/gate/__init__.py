#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/gate/__init__.py
"""``scitex-dev gate`` CLI package."""

from ._cmd import register_gate_command

__all__ = ["register_gate_command"]
