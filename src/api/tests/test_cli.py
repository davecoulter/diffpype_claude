import argparse
from unittest.mock import MagicMock

import pytest

from src.cli import (
    _elapsed_label,
    _entity_to_dict,
    _print_entity_table,
    build_parser,
    cmd_get_dummy,
    cmd_reset_db,
    cmd_run_dummy,
    cmd_seed_db,
    main,
)


def test_entity_to_dict_serializes_sqlalchemy_object():
    col_id = MagicMock()
    col_id.name = "id"
    col_status = MagicMock()
    col_status.name = "status"
    entity = MagicMock()
    entity.__table__ = MagicMock()
    entity.__table__.columns = [col_id, col_status]
    entity.id = 7
    entity.status = "complete"
    del entity.model_dump  # ensure the ORM branch is taken

    result = _entity_to_dict(entity)

    assert result == {"id": 7, "status": "complete"}


def test_entity_to_dict_serializes_pydantic_model():
    from src.api.schemas import DummyImageStatus

    model = DummyImageStatus(id=3, status="pending", latest_job_id=None)

    result = _entity_to_dict(model)

    assert result == {
        "id": 3,
        "status": "pending",
        "latest_job_id": None,
        "created_at": None,
        "job_started_at": None,
        "job_finished_at": None,
    }


def test_print_entity_table_outputs_column_headers_and_values(mocker, capsys):
    col = MagicMock()
    col.name = "id"
    entity = MagicMock()
    entity.__table__ = MagicMock()
    entity.__table__.columns = [col]
    entity.id = 42
    del entity.model_dump

    _print_entity_table([entity])

    out = capsys.readouterr().out
    assert "id" in out
    assert "42" in out


def test_parser_recognises_get_dummy_command():
    args = build_parser().parse_args(["get-dummy", "--id", "5"])
    assert args.command == "get-dummy"
    assert args.id == 5


def test_main_routes_get_dummy_to_cmd_get_dummy(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_get_dummy")
    main(["get-dummy", "--id", "1"])
    mock_cmd.assert_called_once()


def test_cmd_get_dummy_prints_table_for_found_image(mocker, capsys):
    from src.db.models import DummyImage

    fake_image = DummyImage(id=5, status="complete", latest_job_id="abc-123")
    mocker.patch("src.services.job_service.get_dummy_job", return_value=fake_image)
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_get_dummy(argparse.Namespace(command="get-dummy", id=5))

    out = capsys.readouterr().out
    assert "5" in out
    assert "complete" in out


def test_cmd_get_dummy_prints_error_for_missing_image(mocker, capsys):
    mocker.patch("src.services.job_service.get_dummy_job", return_value=None)
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_get_dummy(argparse.Namespace(command="get-dummy", id=999))

    out = capsys.readouterr().out
    assert "999" in out
    assert "Error" in out


def test_cmd_get_dummy_closes_session(mocker):
    mocker.patch("src.services.job_service.get_dummy_job", return_value=None)
    mock_session = MagicMock()
    mocker.patch("src.db.session.SessionLocal", return_value=mock_session)

    cmd_get_dummy(argparse.Namespace(command="get-dummy", id=1))

    mock_session.close.assert_called_once()


def test_elapsed_label_run_time_when_finished():
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
    image = MagicMock(
        job_started_at=start,
        job_finished_at=start + timedelta(seconds=75),
        created_at=start,
    )

    assert _elapsed_label(image) == "Run Time: 1m 15s"


def test_elapsed_label_run_time_when_still_running():
    from datetime import datetime, timedelta, timezone

    started = datetime.now(timezone.utc) - timedelta(seconds=5)
    image = MagicMock(job_started_at=started, job_finished_at=None, created_at=started)

    assert _elapsed_label(image).startswith("Run Time:")


def test_elapsed_label_queue_time_when_pending():
    from datetime import datetime, timedelta, timezone

    created = datetime.now(timezone.utc) - timedelta(seconds=3)
    image = MagicMock(job_started_at=None, job_finished_at=None, created_at=created)

    assert _elapsed_label(image).startswith("Queue Time:")


def test_elapsed_label_none_when_no_timestamps():
    image = MagicMock(job_started_at=None, job_finished_at=None, created_at=None)

    assert _elapsed_label(image) is None


def test_cmd_get_dummy_prints_elapsed_run_time(mocker, capsys):
    from datetime import datetime, timedelta, timezone

    from src.db.models import DummyImage

    start = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
    fake_image = DummyImage(
        id=5,
        status="complete",
        latest_job_id="abc-123",
        job_started_at=start,
        job_finished_at=start + timedelta(seconds=30),
    )
    mocker.patch("src.services.job_service.get_dummy_job", return_value=fake_image)
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_get_dummy(argparse.Namespace(command="get-dummy", id=5))

    out = capsys.readouterr().out
    assert "Run Time: 30s" in out


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
