#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Side effect declaration for mutation operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SideEffectType = Literal[
    "file_create",
    "file_modify",
    "file_delete",
    "network",
    "state_change",
    "cache_write",
]


@dataclass(frozen=True)
class SideEffect:
    """A declared side effect of a function.

    Attributes
    ----------
    type : str
        Category (file_create, file_modify, file_delete, network,
        state_change, cache_write).
    target : str
        What is affected (file path, URL, description).
    undoable : bool
        Whether the effect can be reversed.
    """

    type: SideEffectType
    target: str
    undoable: bool = False

    def __str__(self) -> str:
        return f"{self.type}: {self.target}"


# EOF
