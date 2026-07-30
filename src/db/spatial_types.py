"""Native PostgreSQL range-family column types for HEALPix spatial indexing.

This module vendors the *design* of the unmaintained ``healpix-alchemy`` package
(https://github.com/skyportal/healpix-alchemy) — specifically its idea of encoding
HEALPix geometry as native integer ranges so spatial overlap becomes an indexed
numeric-range operation in the database rather than a string deserialization in
Python. It does **not** depend on that package: as of 2026 ``healpix-alchemy==1.0.1``
(unmaintained since 2021) fails to import against modern ``mocpy`` because it
references ``mocpy.IntervalSet``, an API mocpy has since removed (see GitHub issue
#26).

Two column types live here:

* ``MOCType`` — an areal footprint (a *set* of disjoint cells) stored as
  ``INT8MULTIRANGE``. "What area does this cover?"
* ``PointHEALPixType`` — a single point's containing cell stored as a one-cell
  ``INT8RANGE`` ``[i, i+1)``. "Which single cell does this belong to?" These are
  deliberately separate columns even though both are range-backed: a footprint and
  a point-membership index answer different queries, and a point cell can be tested
  for containment against a footprint on another table with ``footprint @>
  healpix_index`` (an indexed ``int8multirange @> int8range`` operation).

Two deliberate departures from the original 2021 design, both forced by newer
infrastructure:

* **Single multirange/range column instead of a one-row-per-interval child table.**
  PostgreSQL multirange types (PG14+, Sept 2021) hold an entire MOC — a set of
  disjoint ranges — in one column value, so a footprint stays a single field on its
  owning row instead of exploding into a normalized side table. We target
  PostgreSQL 16.
* **``mocpy.MOC.to_depth29_ranges`` / ``from_depth29_ranges`` instead of
  ``astropy_healpix.uniq_to_level_ipix``.** Modern mocpy exposes the depth-29 range
  conversion directly, so no separate ``astropy-healpix`` dependency is needed.

Since the project migrated to ``psycopg`` v3 (doc 29), both types bind and read
native SQLAlchemy ``Range``/``MultiRange`` objects directly — psycopg3 adapts them
to/from PostgreSQL range types without the text-literal (``{[lo,hi),...}``)
serialization and regex parsing psycopg2 required.
"""

from __future__ import annotations

from collections.abc import Sequence

import astropy.units as u
import numpy as np
import sqlalchemy as sa
from mocpy import MOC
from sqlalchemy.dialects.postgresql import INT8MULTIRANGE, INT8RANGE, MultiRange, Range

MAX_DEPTH = 29
"""HEALPix order every cell is normalized to for storage.

This is the finest order whose NESTED pixel indices still fit in a signed 8-byte
integer: ``npix = 12 * 4**29 ≈ 3.46e18`` is below the ``bigint`` ceiling of
``2**63 - 1 ≈ 9.22e18``, whereas order 30 would overflow. Normalizing every cell
to one common order places all footprints on a single index axis, which is what
lets spatial overlap reduce to native integer-range intersection.
"""


class MOCType(sa.TypeDecorator):
    """SQLAlchemy column type that persists a ``mocpy.MOC`` as a native ``int8multirange``."""

    impl = INT8MULTIRANGE
    cache_ok = True

    def process_bind_param(self, value: MOC | None, dialect) -> MultiRange | None:
        """Encode a MOC into a native multirange of depth-29 ``[lo, hi)`` intervals."""
        if value is None:
            return None
        return MultiRange(
            [Range(int(lo), int(hi), bounds="[)") for lo, hi in value.to_depth29_ranges]
        )

    def process_result_value(self, value, dialect) -> MOC | None:
        """Decode a stored multirange back into an equivalent MOC covering the same sky."""
        if value is None:
            return None
        if not value:
            return MOC.new_empty(MAX_DEPTH)
        ranges = np.array([(r.lower, r.upper) for r in value], dtype=np.uint64)
        return MOC.from_depth29_ranges(MAX_DEPTH, ranges)

    def compare_values(self, x, y) -> bool:
        """Report whether two footprints are the same for ORM change detection.

        Overridden because mocpy's ``MOC.__eq__`` raises ``TypeError`` when a MOC
        is compared to a non-MOC (which SQLAlchemy does on every flush — passing
        ``None`` or the ``NO_VALUE`` sentinel for never-loaded columns), and
        because equality here should mean "stores identically" — i.e. covers the
        same sky at depth 29 — regardless of the MOC's original authoring order.
        Any operand that is not a MOC (``None``, ``NO_VALUE``, etc.) falls back to
        identity comparison.
        """
        if not isinstance(x, MOC) or not isinstance(y, MOC):
            return x is y
        return np.array_equal(x.to_depth29_ranges, y.to_depth29_ranges)


class PointHEALPixType(sa.TypeDecorator):
    """SQLAlchemy column type storing a point's depth-29 HEALPix cell as a one-cell ``int8range``.

    Binds a plain ``(ra_deg, decl_deg)`` tuple: the type computes the containing
    depth-29 NESTED cell ``i`` and persists the single-cell range ``[i, i+1)``, so
    service callers assign coordinates directly without a separate precompute step.
    Reads back the integer cell index ``i`` (the range's lower bound) — the bind/read
    representations differ deliberately, mirroring how the column is *written* from a
    coordinate but *queried* as a cell. ``None`` passes through unchanged so a row
    without coordinates (e.g. a ``Level3Mosaic`` with no constituent calibrations
    yet) persists and reads back ``NULL``.
    """

    impl = INT8RANGE
    cache_ok = True

    def process_bind_param(
        self, value: tuple[float, float] | None, dialect
    ) -> Range | None:
        """Encode a ``(ra, decl)`` tuple into its single-cell depth-29 ``[i, i+1)`` range."""
        if value is None:
            return None
        ra_deg, decl_deg = value
        cell = _point_to_depth29_cell(ra_deg, decl_deg)
        return Range(cell, cell + 1, bounds="[)")

    def process_result_value(self, value, dialect) -> int | None:
        """Decode a stored single-cell range back into its integer depth-29 cell index."""
        if value is None:
            return None
        return int(value.lower)


def _point_to_depth29_cell(ra_deg: float, decl_deg: float) -> int:
    """Return the depth-29 NESTED HEALPix cell index containing the given sky point."""
    moc = MOC.from_lonlat(
        np.array([ra_deg]) * u.deg,
        np.array([decl_deg]) * u.deg,
        max_norder=MAX_DEPTH,
    )
    return int(moc.to_depth29_ranges[0][0])


def union_mocs(mocs: Sequence[MOC]) -> MOC:
    """Return the union of a non-empty sequence of MOCs.

    The single shared implementation of "combine these footprints into one" —
    consumed by both ``mosaic_service`` (constituent-calibration footprint union)
    and ``tile_service`` (project-footprint region derivation), replacing the
    prototype's ``DataUtils.Get_Unioned_MOC``.
    """
    union = mocs[0]
    for moc in mocs[1:]:
        union = union.union(moc)
    return union


def moc_to_ranges(moc: MOC | None) -> list[tuple[int, int]] | None:
    """Convert a MOC to a plain list of depth-29 ``[lo, hi)`` integer range pairs.

    The wire-safe representation for a footprint at every Pydantic/API/CLI
    boundary: exactly the ranges ``MOCType`` binds/reads at the DB boundary, so
    there is no separate encode/decode logic and no fidelity loss.
    """
    if moc is None:
        return None
    return [(int(lo), int(hi)) for lo, hi in moc.to_depth29_ranges]


def ranges_to_moc(ranges: list[tuple[int, int]] | None) -> MOC | None:
    """Convert a plain list of depth-29 ``[lo, hi)`` integer range pairs back to a MOC."""
    if ranges is None:
        return None
    if not ranges:
        return MOC.new_empty(MAX_DEPTH)
    array = np.array(ranges, dtype=np.uint64)
    return MOC.from_depth29_ranges(MAX_DEPTH, array)
