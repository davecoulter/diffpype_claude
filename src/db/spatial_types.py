"""Native PostgreSQL range-family column type for storing HEALPix MOC footprints.

This module vendors the *design* of the unmaintained ``healpix-alchemy`` package
(https://github.com/skyportal/healpix-alchemy) — specifically its idea of encoding
a HEALPix Multi-Order Coverage map (MOC) as native integer ranges so spatial
overlap becomes an indexed numeric-range operation in the database rather than a
string deserialization in Python. It does **not** depend on that package: as of
2026 ``healpix-alchemy==1.0.1`` (unmaintained since 2021) fails to import against
modern ``mocpy`` because it references ``mocpy.IntervalSet``, an API mocpy has
since removed (see GitHub issue #26).

Three deliberate departures from the original design, all forced by newer
infrastructure than existed in 2021:

* **Single ``INT8MULTIRANGE`` column instead of a one-row-per-interval child
  table.** PostgreSQL multirange types (PG14+, Sept 2021) can hold an entire MOC
  — a *set* of disjoint ranges — in one column value, so a footprint stays a
  single field on its owning row instead of exploding into a normalized side
  table. We target PostgreSQL 16.
* **``mocpy.MOC.to_depth29_ranges`` / ``from_depth29_ranges`` instead of
  ``astropy_healpix.uniq_to_level_ipix``.** Modern mocpy exposes the depth-29
  range conversion directly, so no separate ``astropy-healpix`` dependency is
  needed.
* **Bind/read as the multirange text literal, not SQLAlchemy ``Range`` objects.**
  The project's driver is ``psycopg2``, which has no adapter for multirange
  types (that support only landed in ``psycopg`` v3). We therefore hand psycopg2
  the Postgres text form ``{[lo,hi),...}`` — which SQLAlchemy already wraps in an
  ``::int8multirange`` cast — and parse the same form back on read.
"""

from __future__ import annotations

import re

import numpy as np
import sqlalchemy as sa
from mocpy import MOC
from sqlalchemy.dialects.postgresql import INT8MULTIRANGE

MAX_DEPTH = 29
"""HEALPix order every cell is normalized to for storage.

This is the finest order whose NESTED pixel indices still fit in a signed 8-byte
integer: ``npix = 12 * 4**29 ≈ 3.46e18`` is below the ``bigint`` ceiling of
``2**63 - 1 ≈ 9.22e18``, whereas order 30 would overflow. Normalizing every cell
to one common order places all footprints on a single index axis, which is what
lets spatial overlap reduce to native integer-range intersection.
"""

_RANGE_RE = re.compile(r"\[(\d+),(\d+)\)")


class MOCType(sa.TypeDecorator):
    """SQLAlchemy column type that persists a ``mocpy.MOC`` as a native ``int8multirange``."""

    impl = INT8MULTIRANGE
    cache_ok = True

    def process_bind_param(self, value: MOC | None, dialect) -> str | None:
        """Encode a MOC into a ``{[lo,hi),...}`` multirange literal of depth-29 intervals."""
        if value is None:
            return None
        intervals = "".join(
            f"[{int(lo)},{int(hi)})," for lo, hi in value.to_depth29_ranges
        )
        return "{" + intervals.rstrip(",") + "}"

    def process_result_value(self, value: str | None, dialect) -> MOC | None:
        """Decode a stored multirange literal back into an equivalent MOC covering the same sky."""
        if value is None:
            return None
        pairs = _RANGE_RE.findall(value)
        if not pairs:
            return MOC.new_empty(MAX_DEPTH)
        ranges = np.array(pairs, dtype=np.uint64)
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
