import argparse
import sys


def cmd_seed_db(args: argparse.Namespace) -> None:
    from src.db.seed import seed_step_definitions

    print("Seeding database: inserting foundational StepDefinition records...")
    seed_step_definitions()
    print("Done.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diffpype-cli",
        description="DevOps CLI for Diffpype administrative tasks.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    subparsers.add_parser("seed-db", help="Seed foundational records into the database.")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "seed-db":
        cmd_seed_db(args)


if __name__ == "__main__":
    main(sys.argv[1:])
