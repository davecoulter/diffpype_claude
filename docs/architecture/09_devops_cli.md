##### 09: DevOps CLI & Database Management
**Version:** 0.1

###### Preamble
This document introduces a formal Command Line Interface (CLI) for DevOps tasks, specifically database seeding, to replace manual inline Python execution. This aligns with the system architecture defining the API boundary as the entry point for the CLI.

###### 1. CLI Implementation
*   **Directive:** Create a formal CLI entry point for administrative tasks using built-in libraries to keep the skeleton thin.
*   **Behavior:** Create a new module at `src/cli.py`. Use Python's built-in `argparse` library to create a command routing structure (do not add new dependencies like `click` or `typer` yet). Add an `if __name__ == "__main__":` block so the script can be executed directly.

###### 2. Database Seeding Hook
*   **Directive:** Safely trigger the seeding of foundational database records from the command line.
*   **Behavior:** Implement a `seed-db` command within the CLI that imports and executes `src.db.seed.seed_step_definitions()`. The CLI must clearly log its actions to stdout so the user knows what was seeded.

###### 3. CLI Testing
*   **Directive:** Ensure the CLI arguments and command routing are covered by the test suite.
*   **Behavior:** Add a test module (e.g., `src/api/tests/test_cli.py`) to verify the CLI parses the `seed-db` command correctly and triggers the seed function using `pytest-mock`.

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### CLI Implementation, seed-db Command, & Tests
*   **`src/cli.py`:** Created with `argparse`. `build_parser()` constructs a top-level parser with a `subparsers` group (`dest="command"`, `required=True`) and registers the `seed-db` subcommand. `cmd_seed_db()` performs a deferred `from src.db.seed import seed_step_definitions` import (keeps boot-time imports minimal), prints a start message, calls the function, then prints `"Done."`. `main(argv)` dispatches to the correct command handler; the `if __name__ == "__main__":` guard passes `sys.argv[1:]` to `main`.
*   **`src/api/tests/test_cli.py`:** 5 tests using `pytest-mock`: (1) parser accepts `seed-db` and sets `args.command`; (2) missing subcommand raises `SystemExit`; (3) `main(["seed-db"])` routes to `cmd_seed_db` (patches the handler directly); (4) `cmd_seed_db` calls `seed_step_definitions` exactly once (patches `src.db.seed.seed_step_definitions` to intercept the deferred import); (5) `cmd_seed_db` writes both expected lines to stdout (verified via `capsys`).
*   **Verification:** `pytest src/api/tests/test_cli.py -v` → 5 passed. Full suite → **15 passed, 96.03% coverage**. `src/cli.py` at 95% (line 35, the `__main__` guard, is the sole uncovered line — expected).