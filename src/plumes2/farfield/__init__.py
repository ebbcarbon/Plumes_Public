"""Brooks (1960) far-field dilution, and the standalone far-field calculator."""

from __future__ import annotations

from plumes2.farfield.brooks import (
    BrooksParameters,
    beta,
    dilution_factor,
    initial_eddy_diffusivity,
    width,
)

__all__ = [
    "BrooksParameters",
    "beta",
    "dilution_factor",
    "initial_eddy_diffusivity",
    "width",
]
