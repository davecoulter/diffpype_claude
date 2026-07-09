import argparse
import sys


def _entity_to_dict(entity) -> dict:
    """Serialize a SQLAlchemy ORM object or Pydantic model to a plain dictionary."""
    if hasattr(entity, "model_dump"):
        return entity.model_dump()
    return {col.name: getattr(entity, col.name) for col in entity.__table__.columns}


def _print_entity_table(entities: list) -> None:
    """Print a list of domain entities or Pydantic models as an ASCII grid table."""
    from tabulate import tabulate

    rows = [_entity_to_dict(e) for e in entities]
    print(tabulate(rows, headers="keys", tablefmt="grid"))


def _elapsed_label(image) -> str | None:
    """Return a Run Time or Queue Time label derived from a DummyImage's timestamps."""
    from datetime import datetime, timezone

    def _fmt(delta) -> str:
        total = max(0, int(delta.total_seconds()))
        minutes, seconds = divmod(total, 60)
        return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"

    now = datetime.now(timezone.utc)
    if image.job_started_at is not None:
        end = image.job_finished_at or now
        return f"Run Time: {_fmt(end - image.job_started_at)}"
    if image.created_at is not None:
        return f"Queue Time: {_fmt(now - image.created_at)}"
    return None


def cmd_seed_db(_: argparse.Namespace) -> None:
    """Insert the foundational StepDefinition records into the database."""
    from src.db.seed import seed_step_definitions

    print("Seeding database: inserting foundational StepDefinition records...")
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


def cmd_get_dummy(args: argparse.Namespace) -> None:
    """Fetch a DummyImage by ID from the database and print it as an ASCII table."""
    from src.db.session import SessionLocal
    from src.services import job_service

    db = SessionLocal()
    try:
        image = job_service.get_dummy_job(db, args.id)
    finally:
        db.close()

    if image is None:
        print(f"Error: No DummyImage found with id={args.id}.")
        return

    _print_entity_table([image])
    label = _elapsed_label(image)
    if label:
        print(label)


def cmd_run_dummy(args: argparse.Namespace) -> None:
    """Dispatch a dummy Celery job through the service layer and print its identifiers."""
    from src.db.session import SessionLocal
    from src.services import job_service

    config = {"sleep_duration": args.sleep}

    db = SessionLocal()
    try:
        job_id, image_id = job_service.dispatch_dummy_job(db, config)
    finally:
        db.close()

    print(f"Dispatched dummy job. job_id={job_id}, image_id={image_id}")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser with all diffpype-manage subcommands."""
    parser = argparse.ArgumentParser(
        prog="diffpype-manage",
        description="DevOps CLI for Diffpype administrative tasks.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    subparsers.add_parser("seed-db", help="Seed foundational records into the database.")

    get_dummy = subparsers.add_parser(
        "get-dummy", help="Fetch and display the status of a DummyImage by ID."
    )
    get_dummy.add_argument(
        "--id",
        type=int,
        required=True,
        metavar="ID",
        help="The integer ID of the DummyImage to fetch.",
    )

    subparsers.add_parser(
        "reset-db",
        help="Drop all tables and rebuild the schema from Alembic migrations.",
    )

    run_dummy = subparsers.add_parser(
        "run-dummy", help="Dispatch a dummy Celery job and print the job ID."
    )
    run_dummy.add_argument(
        "--sleep",
        type=int,
        default=5,
        metavar="SECONDS",
        help="Sleep duration in seconds (1-10, default 5).",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and dispatch to the matching command handler."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "seed-db":
        cmd_seed_db(args)
    elif args.command == "get-dummy":
        cmd_get_dummy(args)
    elif args.command == "reset-db":
        cmd_reset_db(args)
    elif args.command == "run-dummy":
        cmd_run_dummy(args)


if __name__ == "__main__":
    main(sys.argv[1:])
