import argparse
from unittest.mock import MagicMock

import pytest

from src.cli import build_parser, cmd_reset_db, cmd_run_dummy, cmd_seed_db, main


def test_parser_recognises_seed_db_command():
    args = build_parser().parse_args(["seed-db"])
    assert args.command == "seed-db"


def test_parser_recognises_run_dummy_command():
    args = build_parser().parse_args(["run-dummy"])
    assert args.command == "run-dummy"
    assert args.sleep == 5


def test_run_dummy_accepts_custom_sleep_arg():
    args = build_parser().parse_args(["run-dummy", "--sleep", "3"])
    assert args.sleep == 3


def test_parser_recognises_reset_db_command():
    args = build_parser().parse_args(["reset-db"])
    assert args.command == "reset-db"


def test_missing_command_exits():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_main_routes_seed_db_to_cmd_seed_db(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_seed_db")
    main(["seed-db"])
    mock_cmd.assert_called_once()


def test_main_routes_run_dummy_to_cmd_run_dummy(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_run_dummy")
    main(["run-dummy"])
    mock_cmd.assert_called_once()


def test_main_routes_reset_db_to_cmd_reset_db(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_reset_db")
    main(["reset-db"])
    mock_cmd.assert_called_once()


def test_cmd_reset_db_runs_downgrade_then_upgrade_then_seed(mocker):
    mocker.patch("alembic.config.Config", return_value="CFG")
    mock_down = mocker.patch("alembic.command.downgrade")
    mock_up = mocker.patch("alembic.command.upgrade")
    mock_seed = mocker.patch("src.cli.cmd_seed_db")
    manager = mocker.MagicMock()
    manager.attach_mock(mock_down, "down")
    manager.attach_mock(mock_up, "up")
    manager.attach_mock(mock_seed, "seed")

    cmd_reset_db(argparse.Namespace(command="reset-db"))

    mock_down.assert_called_once_with("CFG", "base")
    mock_up.assert_called_once_with("CFG", "head")
    # Auto-seed runs last so a freshly reset DB is immediately usable.
    assert [call[0] for call in manager.mock_calls] == ["down", "up", "seed"]


def test_cmd_reset_db_auto_seeds(mocker):
    mocker.patch("alembic.config.Config", return_value="CFG")
    mocker.patch("alembic.command.downgrade")
    mocker.patch("alembic.command.upgrade")
    mock_seed = mocker.patch("src.cli.cmd_seed_db")

    args = argparse.Namespace(command="reset-db")
    cmd_reset_db(args)

    mock_seed.assert_called_once_with(args)


def test_cmd_reset_db_logs_to_stdout(mocker, capsys):
    mocker.patch("alembic.config.Config", return_value="CFG")
    mocker.patch("alembic.command.downgrade")
    mocker.patch("alembic.command.upgrade")
    mocker.patch("src.cli.cmd_seed_db")

    cmd_reset_db(argparse.Namespace(command="reset-db"))

    out = capsys.readouterr().out
    assert "downgrading to base" in out
    assert "upgrading to head" in out
    assert "Auto-seeding" in out


def test_cmd_seed_db_calls_seed_function(mocker):
    mock_seed = mocker.patch("src.db.seed.seed_step_definitions")
    cmd_seed_db(argparse.Namespace(command="seed-db"))
    mock_seed.assert_called_once()


def test_cmd_seed_db_logs_to_stdout(mocker, capsys):
    mocker.patch("src.db.seed.seed_step_definitions")
    cmd_seed_db(argparse.Namespace(command="seed-db"))
    out = capsys.readouterr().out
    assert "Seeding database" in out
    assert "Done" in out


def test_cmd_run_dummy_calls_dispatch_with_config_and_closes_session(mocker):
    mock_dispatch = mocker.patch(
        "src.services.job_service.dispatch_dummy_job",
        return_value=("fake-job-id", 42),
    )
    mock_session = MagicMock()
    mocker.patch("src.db.session.SessionLocal", return_value=mock_session)

    cmd_run_dummy(argparse.Namespace(command="run-dummy", sleep=3))

    mock_dispatch.assert_called_once_with(mock_session, {"sleep_duration": 3})
    mock_session.close.assert_called_once()


def test_cmd_run_dummy_binds_a_valid_uuid_correlation_id(mocker):
    import uuid
    from structlog.contextvars import get_contextvars

    mocker.patch(
        "src.services.job_service.dispatch_dummy_job",
        return_value=("fake-job-id", 42),
    )
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_run_dummy(argparse.Namespace(command="run-dummy", sleep=5))

    ctx = get_contextvars()
    assert "correlation_id" in ctx
    uuid.UUID(ctx["correlation_id"])  # raises ValueError if not a valid UUID


def test_cmd_run_dummy_logs_job_id_to_stdout(mocker, capsys):
    mocker.patch(
        "src.services.job_service.dispatch_dummy_job",
        return_value=("abc-123", 7),
    )
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_run_dummy(argparse.Namespace(command="run-dummy", sleep=5))

    out = capsys.readouterr().out
    assert "abc-123" in out
    assert "7" in out
