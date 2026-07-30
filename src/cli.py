import argparse
import enum
import os
import sys

# All four codes are the same string length ("\033[NNm", 2-digit N) so every
# colorized status cell carries identical invisible overhead — tabulate's width
# calculation ends up uniformly wider than necessary (harmless), never uneven.
_STATUS_ANSI = {
    "pending": "\033[33m",  # yellow
    "in_process": "\033[36m",  # cyan
    "complete": "\033[32m",  # green
    "failed": "\033[31m",  # red
}
_ANSI_RESET = "\033[0m"


def _colors_enabled() -> bool:
    """Colorize only in an interactive terminal, honoring the NO_COLOR convention (no-color.org)."""
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _colorize_status(value: str) -> str:
    """Wrap a known JobStatus string in its ANSI color; unrecognized values pass through unchanged."""
    code = _STATUS_ANSI.get(value)
    return f"{code}{value}{_ANSI_RESET}" if code else value


def _entity_to_dict(entity) -> dict:
    """Serialize a SQLAlchemy ORM object or Pydantic model to a plain dictionary."""
    if hasattr(entity, "model_dump"):
        return entity.model_dump()
    return {col.name: getattr(entity, col.name) for col in entity.__table__.columns}


def _format_moc_for_display(value):
    """Reduce a mocpy.MOC to a compact sq.deg string; pass through any other value unchanged.

    Safety net for any table column that happens to hold a raw MOC (e.g. a
    future status command that surfaces footprint) — tabulate otherwise dumps
    the object's internal repr, which is unreadable and can be enormous.
    """
    from mocpy import MOC

    if isinstance(value, MOC):
        return f"MOC({value.sky_fraction * 41253.0:.4f} sq.deg)"
    return value


def _print_entity_table(entities: list, fields: list[str] | None = None) -> None:
    """Print a list of domain entities or Pydantic models as an ASCII grid table.

    `fields`, if given, restricts and orders the printed columns — use it to
    keep a status-check table salient (e.g. skip bare foreign-key ids that
    aren't meaningful without a join) rather than dumping every column.

    The `status` column is normalized to its plain value (tabulate otherwise
    prints a real enum member as e.g. "JobStatus.COMPLETE", since `str()`/
    `format()` on a `str`+`Enum` mixin doesn't reduce to the bare value) and
    ANSI-colored when stdout is an interactive terminal (and NO_COLOR is
    unset) — plain text otherwise, so piping/redirecting output never leaks
    escape codes into a file or another program. Any raw MOC value is reduced
    to a compact sq.deg string rather than printed as-is.
    """
    from tabulate import tabulate

    rows = [_entity_to_dict(e) for e in entities]
    if fields is not None:
        rows = [{key: row[key] for key in fields} for row in rows]
    colors_on = _colors_enabled()
    for row in rows:
        status = row.get("status")
        if isinstance(status, enum.Enum):
            status = status.value
        if status is not None:
            row["status"] = _colorize_status(status) if colors_on else status
        for key, value in row.items():
            row[key] = _format_moc_for_display(value)
    print(tabulate(rows, headers="keys", tablefmt="grid"))


def cmd_seed_db(_: argparse.Namespace) -> None:
    """Insert the foundational sysadmin and reference-data records into the database."""
    from src.db.seed import seed_step_definitions

    print("Seeding database: inserting foundational sysadmin + reference records...")
    seed_step_definitions()
    print("Done.")


def cmd_reset_db(args: argparse.Namespace) -> None:
    """Drop all tables, rebuild the schema from migrations, and re-seed foundational rows."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")

    print("Resetting database: downgrading to base (dropping all tables)...")
    command.downgrade(cfg, "base")

    print("Rebuilding schema: upgrading to head...")
    command.upgrade(cfg, "head")

    print("Schema reset complete. Auto-seeding foundational records...")
    cmd_seed_db(args)


def cmd_create_project(args: argparse.Namespace) -> None:
    """Create a Project through the service layer and print its identifiers."""
    from src.db.session import SessionLocal
    from src.services import project_service

    db = SessionLocal()
    try:
        try:
            project = project_service.create_project(
                db, args.name, args.description, args.user_id
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            return
    finally:
        db.close()

    print(f"Created project. id={project.id}, slug={project.slug}")


def cmd_ingest(args: argparse.Namespace) -> None:
    """Dispatch an ingest batch through the service layer and print its identifiers."""
    from src.db.session import SessionLocal
    from src.services import ingest_service

    db = SessionLocal()
    try:
        job_id, batch_id = ingest_service.create_ingest_batch(
            db, args.project_id, args.s3_prefix
        )
    finally:
        db.close()

    print(f"Dispatched ingest batch. job_id={job_id}, batch_id={batch_id}")


def cmd_ingest_status(args: argparse.Namespace) -> None:
    """Fetch an IngestBatch by ID from the database and print it as an ASCII table."""
    from src.db.session import SessionLocal
    from src.services import ingest_service

    db = SessionLocal()
    try:
        batch = ingest_service.get_ingest_batch(db, args.id)
    finally:
        db.close()

    if batch is None:
        print(f"Error: No IngestBatch found with id={args.id}.")
        return

    _print_entity_table([batch])


def cmd_sync_staging(args: argparse.Namespace) -> None:
    """Dispatch a staging→canonical storage sync through the service layer and print its job id."""
    from src.services import storage_service

    job_id = storage_service.dispatch_staging_sync(
        args.staging_prefix, args.canonical_prefix
    )
    print(f"Dispatched staging sync. job_id={job_id}")


def cmd_reconcile_stuck_jobs(args: argparse.Namespace) -> None:
    """Fail any job stuck IN_PROCESS past the staleness threshold and print what changed."""
    from src.db.session import SessionLocal
    from src.services import job_service

    db = SessionLocal()
    try:
        if args.threshold_seconds is not None:
            reconciled = job_service.reconcile_stuck_jobs(db, args.threshold_seconds)
        else:
            reconciled = job_service.reconcile_stuck_jobs(db)
    finally:
        db.close()

    print(f"Reconciled {len(reconciled)} stuck job(s).")
    for r in reconciled:
        print(f"  {r['entity']} id={r['id']} (age={r['age_seconds']:.0f}s) -> FAILED")


def _tessellation_region_kwargs(args: argparse.Namespace) -> dict:
    """Collect the region-resolution kwargs from parsed tessellation CLI args."""
    return {
        "ra": args.ra,
        "decl": args.decl,
        "radius_deg": args.radius_deg,
        "project_id": args.region_project_id,
        "min_ra": args.min_ra,
        "max_ra": args.max_ra,
        "min_decl": args.min_decl,
        "max_decl": args.max_decl,
    }


def cmd_tessellate_tiles(args: argparse.Namespace) -> None:
    """Preview a tile tessellation over the requested region and print it, without writing to the DB."""
    from src.db.enums import RegionSource
    from src.db.session import SessionLocal
    from src.services import tile_service

    db = SessionLocal()
    try:
        tiles = tile_service.generate_tessellation_for_region(
            db,
            RegionSource(args.region_source),
            args.tile_side_arcmin,
            args.overlap_arcmin,
            args.overlap_only,
            **_tessellation_region_kwargs(args),
        )
    finally:
        db.close()
    print(f"Generated {len(tiles)} tile(s):")
    for t in tiles:
        print(f"  {t['name']}: ra={t['ra']:.4f}, decl={t['decl']:.4f}")


def cmd_create_tiles(args: argparse.Namespace) -> None:
    """Generate a tile tessellation over the requested region and persist it through the service layer."""
    from src.db.enums import RegionSource
    from src.db.session import SessionLocal
    from src.services import tile_service

    db = SessionLocal()
    try:
        tiles = tile_service.generate_tessellation_for_region(
            db,
            RegionSource(args.region_source),
            args.tile_side_arcmin,
            args.overlap_arcmin,
            args.overlap_only,
            **_tessellation_region_kwargs(args),
        )
        created = tile_service.create_tiles(db, args.project_id, tiles)
    finally:
        db.close()

    print(f"Created {len(created)} tile(s) for project_id={args.project_id}.")


def cmd_cluster_epochs(args: argparse.Namespace) -> None:
    """Preview an MJD-based epoch clustering for a tile+band and print it, without writing."""
    from src.db.session import SessionLocal
    from src.services import epoch_service

    db = SessionLocal()
    try:
        epochs = epoch_service.cluster_epochs(
            db, args.project_id, args.tile_id, args.band_id, args.peak_distance_thresh
        )
    finally:
        db.close()

    print(f"Generated {len(epochs)} epoch(s):")
    for e in epochs:
        print(f"  start_mjd={e['start_mjd']:.2f}, end_mjd={e['end_mjd']:.2f}")


def cmd_create_epochs(args: argparse.Namespace) -> None:
    """Cluster a tile+band's MJDs into epochs and persist them through the service layer."""
    from src.db.session import SessionLocal
    from src.services import epoch_service

    db = SessionLocal()
    try:
        epochs = epoch_service.cluster_epochs(
            db, args.project_id, args.tile_id, args.band_id, args.peak_distance_thresh
        )
        created = epoch_service.create_epochs(db, args.project_id, epochs)
    finally:
        db.close()

    print(f"Created {len(created)} epoch(s) for project_id={args.project_id}.")


def cmd_create_mosaic(args: argparse.Namespace) -> None:
    """Create a Level3Mosaic through the service layer and print its identifiers."""
    from src.db.session import SessionLocal
    from src.services import mosaic_service

    db = SessionLocal()
    try:
        job_id, mosaic_id = mosaic_service.create_mosaic(
            db,
            args.project_id,
            args.tile_id,
            args.epoch_id,
            args.band_id,
            args.instrument_id,
            args.filename,
            args.target_plate_scale,
        )
    finally:
        db.close()

    print(f"Dispatched mosaic. job_id={job_id}, mosaic_id={mosaic_id}")


def cmd_mosaic_status(args: argparse.Namespace) -> None:
    """Fetch a Level3Mosaic by ID from the database and print it as an ASCII table."""
    from src.db.session import SessionLocal
    from src.services import mosaic_service

    db = SessionLocal()
    try:
        mosaic = mosaic_service.get_mosaic(db, args.id)
    finally:
        db.close()

    if mosaic is None:
        print(f"Error: No Level3Mosaic found with id={args.id}.")
        return

    _print_entity_table(
        [mosaic],
        fields=["id", "filename", "status", "ra", "decl", "created_at", "updated_at"],
    )


def _poll_until_terminal(
    fetch_status, label: str, timeout_s: float, interval_s: float = 1.0
):
    """Poll `fetch_status()` (returning a JobStatus) until COMPLETE/FAILED or timeout."""
    import time as _time

    from src.db.enums import JobStatus

    deadline = _time.monotonic() + timeout_s
    while _time.monotonic() < deadline:
        status = fetch_status()
        if status in (JobStatus.COMPLETE, JobStatus.FAILED):
            return status
        _time.sleep(interval_s)
    raise TimeoutError(f"{label} did not reach a terminal state within {timeout_s}s")


def cmd_populate_demo_project(args: argparse.Namespace) -> None:
    """Sequentially invoke Ingest, Tiles, Epochs, and Mosaics to populate one demo project end-to-end.

    Dev/demo tooling only (no API route, matching cmd_reset_db/cmd_seed_db
    precedent). Requires a real --s3-prefix already populated in storage —
    see GitHub issue #34 for the still-outstanding minio-init fiducial seed.
    """
    from src.db.enums import JobStatus
    from src.db.session import SessionLocal
    from src.services import (
        epoch_service,
        ingest_service,
        mosaic_service,
        project_service,
        tile_service,
    )

    db = SessionLocal()
    try:
        project = project_service.create_project(
            db, args.project_name, None, args.user_id
        )
        print(f"Created project. id={project.id}, slug={project.slug}")

        _job_id, batch_id = ingest_service.create_ingest_batch(
            db, project.id, args.s3_prefix
        )
        print(
            f"Dispatched ingest batch. batch_id={batch_id} - waiting for completion..."
        )

        def _ingest_status():
            batch = ingest_service.get_ingest_batch(db, batch_id)
            assert batch is not None, f"IngestBatch {batch_id} disappeared mid-poll"
            return batch.status

        status = _poll_until_terminal(
            _ingest_status, "IngestBatch", args.ingest_timeout
        )
        if status == JobStatus.FAILED:
            print("Ingest batch failed. Aborting.")
            return
        print("Ingest complete.")

        from src.db.enums import RegionSource

        tessellation = tile_service.generate_tessellation_for_region(
            db,
            RegionSource.CONE,
            args.tile_side_arcmin,
            args.overlap_arcmin,
            ra=args.ra,
            decl=args.decl,
            radius_deg=args.radius_deg,
        )
        tiles = tile_service.create_tiles(db, project.id, tessellation)
        print(f"Created {len(tiles)} tile(s).")
        if not tiles:
            print("No tiles generated for the given region. Aborting.")
            return
        best_tile_id = tile_service.tile_with_most_calibrations(
            db, [t.id for t in tiles]
        )
        if best_tile_id is None:
            print(
                "No tile in the tessellated region overlaps any ingested "
                "calibration. Aborting."
            )
            return
        tile = next(t for t in tiles if t.id == best_tile_id)

        epoch_dicts = epoch_service.cluster_epochs(
            db, project.id, tile.id, args.band_id, args.peak_distance_thresh
        )
        epochs = epoch_service.create_epochs(db, project.id, epoch_dicts)
        print(f"Created {len(epochs)} epoch(s).")
        if not epochs:
            print("No epochs generated (no calibrations in range). Aborting.")
            return
        epoch = epochs[0]

        _job_id, mosaic_id = mosaic_service.create_mosaic(
            db,
            project.id,
            tile.id,
            epoch.id,
            args.band_id,
            args.instrument_id,
            filename=f"{project.slug}_mosaic.fits",
            target_plate_scale=args.target_plate_scale,
        )
        print(f"Dispatched mosaic. mosaic_id={mosaic_id} - waiting for completion...")

        def _mosaic_status():
            mosaic = mosaic_service.get_mosaic(db, mosaic_id)
            assert mosaic is not None, f"Level3Mosaic {mosaic_id} disappeared mid-poll"
            return mosaic.status

        status = _poll_until_terminal(
            _mosaic_status, "Level3Mosaic", args.mosaic_timeout
        )
        print(f"Mosaic finished with status={status.value}.")
        print(f"Demo project population complete. project_id={project.id}")
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser with all diffpype-manage subcommands."""
    from src.db.enums import RegionSource

    parser = argparse.ArgumentParser(
        prog="diffpype-manage",
        description="DevOps CLI for Diffpype administrative tasks.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    subparsers.add_parser(
        "seed-db", help="Seed foundational records into the database."
    )

    subparsers.add_parser(
        "reset-db",
        help="Drop all tables and rebuild the schema from Alembic migrations.",
    )

    create_project = subparsers.add_parser(
        "create-project", help="Create a Project with a name-derived, unique slug."
    )
    create_project.add_argument("--name", required=True, help="Project name.")
    create_project.add_argument(
        "--description", default=None, help="Optional project description."
    )
    create_project.add_argument(
        "--user-id", type=int, required=True, help="Owning User's integer ID."
    )

    ingest = subparsers.add_parser(
        "ingest", help="Dispatch an async ingest run over a storage prefix."
    )
    ingest.add_argument(
        "--project-id", type=int, required=True, help="Owning Project's integer ID."
    )
    ingest.add_argument(
        "--s3-prefix", required=True, help="Storage prefix to scan for FITS files."
    )

    ingest_status = subparsers.add_parser(
        "ingest-status", help="Fetch and display the status of an IngestBatch by ID."
    )
    ingest_status.add_argument(
        "--id", type=int, required=True, metavar="ID", help="IngestBatch integer ID."
    )

    sync_staging = subparsers.add_parser(
        "sync-staging",
        help="Dispatch a staging→canonical storage sync (mc mirror) via the worker.",
    )
    sync_staging.add_argument(
        "--staging-prefix",
        required=True,
        help="Staging location (local path or s3:// URI) to mirror from.",
    )
    sync_staging.add_argument(
        "--canonical-prefix",
        default="",
        help="Canonical bucket prefix to mirror into (default: bucket root).",
    )

    reconcile = subparsers.add_parser(
        "reconcile-stuck-jobs",
        help="Fail any job stuck IN_PROCESS past the staleness threshold.",
    )
    reconcile.add_argument(
        "--threshold-seconds",
        type=int,
        default=None,
        help="Staleness threshold in seconds (default: JOB_STALENESS_TIMEOUT_SECONDS).",
    )

    def _add_tessellation_args(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--region-source",
            choices=[r.value for r in RegionSource],
            default=RegionSource.CONE.value,
            help="Region specification mode (default: cone).",
        )
        subparser.add_argument(
            "--tile-side-arcmin",
            type=float,
            required=True,
            help="Tile side length (arcmin).",
        )
        subparser.add_argument(
            "--overlap-arcmin", type=float, default=0.0, help="Tile overlap (arcmin)."
        )
        subparser.add_argument(
            "--overlap-only",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Keep only tiles intersecting the region (default); "
            "--no-overlap-only materializes the full grid.",
        )
        # cone
        subparser.add_argument(
            "--ra", type=float, help="Cone center RA (deg) [region-source=cone]."
        )
        subparser.add_argument(
            "--decl", type=float, help="Cone center Dec (deg) [region-source=cone]."
        )
        subparser.add_argument(
            "--radius-deg", type=float, help="Cone radius (deg) [region-source=cone]."
        )
        # project_footprint
        subparser.add_argument(
            "--region-project-id",
            type=int,
            help="Project whose calibration footprints define the region "
            "[region-source=project_footprint].",
        )
        # bounding_box
        subparser.add_argument(
            "--min-ra", type=float, help="Min RA (deg) [region-source=bounding_box]."
        )
        subparser.add_argument(
            "--max-ra", type=float, help="Max RA (deg) [region-source=bounding_box]."
        )
        subparser.add_argument(
            "--min-decl", type=float, help="Min Dec (deg) [region-source=bounding_box]."
        )
        subparser.add_argument(
            "--max-decl", type=float, help="Max Dec (deg) [region-source=bounding_box]."
        )

    tessellate_tiles = subparsers.add_parser(
        "tessellate-tiles",
        help="Preview a tile tessellation over a cone region, without writing to the DB.",
    )
    _add_tessellation_args(tessellate_tiles)

    create_tiles = subparsers.add_parser(
        "create-tiles",
        help="Generate and persist a tile tessellation over a cone region.",
    )
    create_tiles.add_argument(
        "--project-id", type=int, required=True, help="Owning Project's integer ID."
    )
    _add_tessellation_args(create_tiles)

    def _add_epoch_cluster_args(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--project-id", type=int, required=True, help="Owning Project's integer ID."
        )
        subparser.add_argument(
            "--tile-id",
            type=int,
            required=True,
            help="Tile integer ID to cluster over.",
        )
        subparser.add_argument(
            "--band-id",
            type=int,
            required=True,
            help="Band integer ID to cluster over.",
        )
        subparser.add_argument(
            "--peak-distance-thresh",
            type=float,
            required=True,
            help="Minimum MJD spacing between histogram peaks to count as a new epoch.",
        )

    cluster_epochs = subparsers.add_parser(
        "cluster-epochs",
        help="Preview an MJD-based epoch clustering for a tile+band, without writing to the DB.",
    )
    _add_epoch_cluster_args(cluster_epochs)

    create_epochs = subparsers.add_parser(
        "create-epochs", help="Cluster a tile+band's MJDs into epochs and persist them."
    )
    _add_epoch_cluster_args(create_epochs)

    create_mosaic = subparsers.add_parser(
        "create-mosaic",
        help="Create a Level3Mosaic job-metadata row and dispatch its drizzle task.",
    )
    create_mosaic.add_argument("--project-id", type=int, required=True)
    create_mosaic.add_argument("--tile-id", type=int, required=True)
    create_mosaic.add_argument("--epoch-id", type=int, required=True)
    create_mosaic.add_argument("--band-id", type=int, required=True)
    create_mosaic.add_argument("--instrument-id", type=int, required=True)
    create_mosaic.add_argument("--filename", required=True)
    create_mosaic.add_argument("--target-plate-scale", type=float, required=True)

    mosaic_status = subparsers.add_parser(
        "mosaic-status", help="Fetch and display the status of a Level3Mosaic by ID."
    )
    mosaic_status.add_argument(
        "--id", type=int, required=True, metavar="ID", help="Level3Mosaic integer ID."
    )

    populate_demo = subparsers.add_parser(
        "populate-demo-project",
        help="Sequentially ingest, tile, cluster, and mosaic one demo project end-to-end.",
    )
    populate_demo.add_argument("--project-name", required=True)
    populate_demo.add_argument("--user-id", type=int, required=True)
    populate_demo.add_argument(
        "--s3-prefix",
        required=True,
        help="Storage prefix already populated with FITS files.",
    )
    populate_demo.add_argument("--ra", type=float, required=True)
    populate_demo.add_argument("--decl", type=float, required=True)
    populate_demo.add_argument("--radius-deg", type=float, required=True)
    populate_demo.add_argument("--tile-side-arcmin", type=float, default=6.0)
    populate_demo.add_argument("--overlap-arcmin", type=float, default=0.0)
    populate_demo.add_argument("--band-id", type=int, required=True)
    populate_demo.add_argument("--instrument-id", type=int, required=True)
    populate_demo.add_argument("--peak-distance-thresh", type=float, default=5.0)
    populate_demo.add_argument("--target-plate-scale", type=float, default=0.03)
    populate_demo.add_argument("--ingest-timeout", type=float, default=120.0)
    populate_demo.add_argument("--mosaic-timeout", type=float, default=60.0)

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and dispatch to the matching command handler."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "seed-db":
        cmd_seed_db(args)
    elif args.command == "reset-db":
        cmd_reset_db(args)
    elif args.command == "create-project":
        cmd_create_project(args)
    elif args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "ingest-status":
        cmd_ingest_status(args)
    elif args.command == "sync-staging":
        cmd_sync_staging(args)
    elif args.command == "reconcile-stuck-jobs":
        cmd_reconcile_stuck_jobs(args)
    elif args.command == "tessellate-tiles":
        cmd_tessellate_tiles(args)
    elif args.command == "create-tiles":
        cmd_create_tiles(args)
    elif args.command == "cluster-epochs":
        cmd_cluster_epochs(args)
    elif args.command == "create-epochs":
        cmd_create_epochs(args)
    elif args.command == "create-mosaic":
        cmd_create_mosaic(args)
    elif args.command == "mosaic-status":
        cmd_mosaic_status(args)
    elif args.command == "populate-demo-project":
        cmd_populate_demo_project(args)


if __name__ == "__main__":
    main(sys.argv[1:])
