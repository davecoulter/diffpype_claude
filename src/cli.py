import argparse
import sys


def cmd_seed_db(_: argparse.Namespace) -> None:
    from src.db.seed import seed_step_definitions

    print("Seeding database: inserting foundational StepDefinition records...")
    seed_step_definitions()
    print("Done.")


def cmd_reset_db(_: argparse.Namespace) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")

    print("Resetting database: downgrading to base (dropping all tables)...")
    command.downgrade(cfg, "base")

    print("Rebuilding schema: upgrading to head...")
    command.upgrade(cfg, "head")

    print("Done. Database schema reset.")


def cmd_run_dummy(args: argparse.Namespace) -> None:
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
    parser = argparse.ArgumentParser(
        prog="diffpype-manage",
        description="DevOps CLI for Diffpype administrative tasks.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    subparsers.add_parser("seed-db", help="Seed foundational records into the database.")

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
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "seed-db":
        cmd_seed_db(args)
    elif args.command == "reset-db":
        cmd_reset_db(args)
    elif args.command == "run-dummy":
        cmd_run_dummy(args)


if __name__ == "__main__":
    main(sys.argv[1:])
