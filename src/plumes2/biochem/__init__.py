"""Dissolved oxygen and biochemical oxygen demand — the last of Phase 4.

One module, `do_bod`, and the split inside it matters more than the module boundary: the near-field
half is **measured** against five archived traces, and the far-field half has **no reference data at
all** and is implemented from the manual with that stated at every entry point.
"""

from __future__ import annotations

from plumes2.biochem.do_bod import (
    far_field_oxygen,
    near_field_oxygen,
    rate_at_temperature,
    ultimate_bod,
)

__all__ = [
    "far_field_oxygen",
    "near_field_oxygen",
    "rate_at_temperature",
    "ultimate_bod",
]
