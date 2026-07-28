import argparse
from unittest.mock import MagicMock

import pytest

from src.cli import (
    _colorize_status,
    _colors_enabled,
    _elapsed_label,
    _entity_to_dict,
    _format_moc_for_display,
    _poll_until_terminal,
    _print_entity_table,
    build_parser,
    cmd_cluster_epochs,
    cmd_create_epochs,
    cmd_create_mosaic,
    cmd_create_project,
    cmd_create_tiles,
    cmd_get_dummy,
    cmd_ingest,
    cmd_ingest_status,
    cmd_mosaic_status,
    cmd_populate_demo_project,
    cmd_reset_db,
    cmd_run_dummy,
    cmd_seed_db,
    cmd_tessellate_tiles,
    main,
)
from src.db.enums import JobStatus


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


def test_format_moc_for_display_reduces_moc_to_compact_sq_deg_string():
    import astropy.units as u
    from mocpy import MOC

    moc = MOC.from_cone(lon=10 * u.deg, lat=0 * u.deg, radius=1 * u.deg, max_depth=10)

    result = _format_moc_for_display(moc)

    assert result.startswith("MOC(")
    assert "sq.deg)" in result


def test_format_moc_for_display_passes_through_non_moc_values():
    assert _format_moc_for_display(42) == 42
    assert _format_moc_for_display(None) is None
    assert _format_moc_for_display("pending") == "pending"


def test_print_entity_table_restricts_and_orders_columns_when_fields_given(capsys):
    cols = []
    for name in ("id", "filename", "footprint", "status"):
        col = MagicMock()
        col.name = name
        cols.append(col)
    entity = MagicMock()
    entity.__table__ = MagicMock()
    entity.__table__.columns = cols
    entity.id = 1
    entity.filename = "x.fits"
    entity.footprint = "raw-moc-object"
    entity.status = "pending"
    del entity.model_dump

    _print_entity_table([entity], fields=["id", "status"])

    out = capsys.readouterr().out
    assert "filename" not in out
    assert "footprint" not in out
    assert "id" in out and "status" in out


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


def test_colors_enabled_false_when_not_a_tty(mocker):
    mocker.patch("sys.stdout.isatty", return_value=False)
    assert _colors_enabled() is False


def test_colors_enabled_false_when_no_color_set(mocker):
    mocker.patch("sys.stdout.isatty", return_value=True)
    mocker.patch.dict("os.environ", {"NO_COLOR": "1"})
    assert _colors_enabled() is False


def test_colors_enabled_true_in_a_plain_tty(mocker):
    mocker.patch("sys.stdout.isatty", return_value=True)
    mocker.patch.dict("os.environ", {}, clear=True)
    assert _colors_enabled() is True


@pytest.mark.parametrize(
    "status,color_code",
    [
        ("pending", "\033[33m"),
        ("in_process", "\033[36m"),
        ("complete", "\033[32m"),
        ("failed", "\033[31m"),
    ],
)
def test_colorize_status_wraps_known_statuses(status, color_code):
    assert _colorize_status(status) == f"{color_code}{status}\033[0m"


def test_colorize_status_passes_through_unknown_value():
    assert _colorize_status("some_new_status") == "some_new_status"


def _make_status_entity(status):
    """A MagicMock shaped like a real ORM row, carrying a genuine JobStatus enum member."""
    col_id, col_status = MagicMock(), MagicMock()
    col_id.name, col_status.name = "id", "status"
    entity = MagicMock()
    entity.__table__ = MagicMock()
    entity.__table__.columns = [col_id, col_status]
    entity.id = 1
    entity.status = status
    del entity.model_dump
    return entity


def test_print_entity_table_normalizes_real_enum_member_to_its_value(capsys):
    """Regression: tabulate previously printed a real enum member as "JobStatus.COMPLETE"."""
    _print_entity_table([_make_status_entity(JobStatus.COMPLETE)])

    out = capsys.readouterr().out
    assert "complete" in out
    assert "JobStatus" not in out


def test_print_entity_table_colorizes_status_when_colors_enabled(mocker, capsys):
    mocker.patch("src.cli._colors_enabled", return_value=True)

    _print_entity_table([_make_status_entity(JobStatus.COMPLETE)])

    out = capsys.readouterr().out
    assert "\033[32m" in out
    assert "\033[0m" in out


def test_print_entity_table_leaves_status_plain_when_colors_disabled(mocker, capsys):
    mocker.patch("src.cli._colors_enabled", return_value=False)

    _print_entity_table([_make_status_entity(JobStatus.COMPLETE)])

    out = capsys.readouterr().out
    assert "\033[" not in out
    assert "complete" in out


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


def test_parser_recognises_create_project_command():
    args = build_parser().parse_args(
        ["create-project", "--name", "My Survey", "--user-id", "1"]
    )
    assert args.command == "create-project"
    assert args.name == "My Survey"
    assert args.description is None
    assert args.user_id == 1


def test_main_routes_create_project_to_cmd_create_project(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_create_project")
    main(["create-project", "--name", "My Survey", "--user-id", "1"])
    mock_cmd.assert_called_once()


def test_cmd_create_project_prints_id_and_slug(mocker, capsys):
    from src.db.models import Project

    fake_project = Project(id=3, name="My Survey", slug="my-survey", user_id=1)
    mocker.patch(
        "src.services.project_service.create_project", return_value=fake_project
    )
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_create_project(
        argparse.Namespace(
            command="create-project",
            name="My Survey",
            description=None,
            user_id=1,
        )
    )

    out = capsys.readouterr().out
    assert "id=3" in out
    assert "slug=my-survey" in out


def test_cmd_create_project_prints_error_on_slug_collision(mocker, capsys):
    mocker.patch(
        "src.services.project_service.create_project",
        side_effect=ValueError("A project with slug 'my-survey' already exists"),
    )
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_create_project(
        argparse.Namespace(
            command="create-project",
            name="My Survey",
            description=None,
            user_id=1,
        )
    )

    out = capsys.readouterr().out
    assert "Error" in out
    assert "already exists" in out


def test_cmd_create_project_closes_session(mocker):
    mocker.patch(
        "src.services.project_service.create_project",
        return_value=MagicMock(id=1, slug="x"),
    )
    mock_session = MagicMock()
    mocker.patch("src.db.session.SessionLocal", return_value=mock_session)

    cmd_create_project(
        argparse.Namespace(
            command="create-project",
            name="My Survey",
            description=None,
            user_id=1,
        )
    )

    mock_session.close.assert_called_once()


def test_parser_recognises_ingest_command():
    args = build_parser().parse_args(
        ["ingest", "--project-id", "1", "--s3-prefix", "raw/"]
    )
    assert args.command == "ingest"
    assert args.project_id == 1
    assert args.s3_prefix == "raw/"


def test_main_routes_ingest_to_cmd_ingest(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_ingest")
    main(["ingest", "--project-id", "1", "--s3-prefix", "raw/"])
    mock_cmd.assert_called_once()


def test_cmd_ingest_calls_service_and_prints_ids(mocker, capsys):
    mocker.patch(
        "src.services.ingest_service.create_ingest_batch",
        return_value=("task-abc", 9),
    )
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_ingest(argparse.Namespace(command="ingest", project_id=1, s3_prefix="raw/"))

    out = capsys.readouterr().out
    assert "task-abc" in out
    assert "9" in out


def test_parser_recognises_ingest_status_command():
    args = build_parser().parse_args(["ingest-status", "--id", "9"])
    assert args.command == "ingest-status"
    assert args.id == 9


def test_main_routes_ingest_status_to_cmd_ingest_status(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_ingest_status")
    main(["ingest-status", "--id", "9"])
    mock_cmd.assert_called_once()


def test_cmd_ingest_status_prints_table_for_found_batch(mocker, capsys):
    from src.db.models import IngestBatch

    fake_batch = IngestBatch(id=9, project_id=1, s3_prefix="raw/", status="complete")
    mocker.patch(
        "src.services.ingest_service.get_ingest_batch", return_value=fake_batch
    )
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_ingest_status(argparse.Namespace(command="ingest-status", id=9))

    out = capsys.readouterr().out
    assert "9" in out
    assert "complete" in out


def test_cmd_ingest_status_prints_error_for_missing_batch(mocker, capsys):
    mocker.patch("src.services.ingest_service.get_ingest_batch", return_value=None)
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_ingest_status(argparse.Namespace(command="ingest-status", id=404))

    out = capsys.readouterr().out
    assert "404" in out
    assert "Error" in out


TESSELLATION_ARGS = [
    "--tile-side-arcmin",
    "6.0",
    "--ra",
    "10.0",
    "--decl",
    "20.0",
    "--radius-deg",
    "0.1",
]


def test_parser_recognises_tessellate_tiles_command():
    args = build_parser().parse_args(["tessellate-tiles", *TESSELLATION_ARGS])
    assert args.command == "tessellate-tiles"
    assert args.tile_side_arcmin == 6.0
    assert args.overlap_arcmin == 0.0


def test_main_routes_tessellate_tiles_to_cmd_tessellate_tiles(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_tessellate_tiles")
    main(["tessellate-tiles", *TESSELLATION_ARGS])
    mock_cmd.assert_called_once()


def test_cmd_tessellate_tiles_prints_generated_tiles(mocker, capsys):
    mocker.patch(
        "src.services.tile_service.generate_tile_tessellation",
        return_value=[
            {"name": "Tile_1", "ra": 10.0, "decl": 20.0},
            {"name": "Tile_2", "ra": 10.1, "decl": 20.1},
        ],
    )

    cmd_tessellate_tiles(
        argparse.Namespace(
            command="tessellate-tiles",
            tile_side_arcmin=6.0,
            ra=10.0,
            decl=20.0,
            radius_deg=0.1,
            overlap_arcmin=0.0,
        )
    )

    out = capsys.readouterr().out
    assert "Generated 2 tile(s)" in out
    assert "Tile_1" in out
    assert "Tile_2" in out


def test_parser_recognises_create_tiles_command():
    args = build_parser().parse_args(
        ["create-tiles", "--project-id", "1", *TESSELLATION_ARGS]
    )
    assert args.command == "create-tiles"
    assert args.project_id == 1


def test_main_routes_create_tiles_to_cmd_create_tiles(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_create_tiles")
    main(["create-tiles", "--project-id", "1", *TESSELLATION_ARGS])
    mock_cmd.assert_called_once()


def test_cmd_create_tiles_persists_and_prints_count(mocker, capsys):
    mocker.patch(
        "src.services.tile_service.generate_tile_tessellation",
        return_value=[{"name": "Tile_1"}, {"name": "Tile_2"}],
    )
    mock_create = mocker.patch(
        "src.services.tile_service.create_tiles",
        return_value=[MagicMock(), MagicMock()],
    )
    mock_session = MagicMock()
    mocker.patch("src.db.session.SessionLocal", return_value=mock_session)

    cmd_create_tiles(
        argparse.Namespace(
            command="create-tiles",
            project_id=3,
            tile_side_arcmin=6.0,
            ra=10.0,
            decl=20.0,
            radius_deg=0.1,
            overlap_arcmin=0.0,
        )
    )

    mock_create.assert_called_once()
    assert mock_create.call_args[0][1] == 3
    mock_session.close.assert_called_once()
    out = capsys.readouterr().out
    assert "Created 2 tile(s) for project_id=3" in out


EPOCH_ARGS = [
    "--project-id",
    "1",
    "--tile-id",
    "2",
    "--band-id",
    "3",
    "--peak-distance-thresh",
    "5.0",
]


def test_parser_recognises_cluster_epochs_command():
    args = build_parser().parse_args(["cluster-epochs", *EPOCH_ARGS])
    assert args.command == "cluster-epochs"
    assert args.tile_id == 2
    assert args.peak_distance_thresh == 5.0


def test_main_routes_cluster_epochs_to_cmd_cluster_epochs(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_cluster_epochs")
    main(["cluster-epochs", *EPOCH_ARGS])
    mock_cmd.assert_called_once()


def test_cmd_cluster_epochs_prints_generated_epochs(mocker, capsys):
    mocker.patch(
        "src.services.epoch_service.cluster_epochs",
        return_value=[{"start_mjd": 60300.0, "end_mjd": 60301.0}],
    )
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_cluster_epochs(
        argparse.Namespace(
            command="cluster-epochs",
            project_id=1,
            tile_id=2,
            band_id=3,
            peak_distance_thresh=5.0,
        )
    )

    out = capsys.readouterr().out
    assert "Generated 1 epoch(s)" in out
    assert "60300.00" in out


def test_parser_recognises_create_epochs_command():
    args = build_parser().parse_args(["create-epochs", *EPOCH_ARGS])
    assert args.command == "create-epochs"


def test_main_routes_create_epochs_to_cmd_create_epochs(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_create_epochs")
    main(["create-epochs", *EPOCH_ARGS])
    mock_cmd.assert_called_once()


def test_cmd_create_epochs_clusters_then_persists_and_prints_count(mocker, capsys):
    mocker.patch(
        "src.services.epoch_service.cluster_epochs",
        return_value=[{"start_mjd": 60300.0, "end_mjd": 60301.0}],
    )
    mock_create = mocker.patch(
        "src.services.epoch_service.create_epochs", return_value=[MagicMock()]
    )
    mock_session = MagicMock()
    mocker.patch("src.db.session.SessionLocal", return_value=mock_session)

    cmd_create_epochs(
        argparse.Namespace(
            command="create-epochs",
            project_id=4,
            tile_id=2,
            band_id=3,
            peak_distance_thresh=5.0,
        )
    )

    mock_create.assert_called_once()
    assert mock_create.call_args[0][1] == 4
    mock_session.close.assert_called_once()
    out = capsys.readouterr().out
    assert "Created 1 epoch(s) for project_id=4" in out


MOSAIC_ARGS = [
    "--project-id",
    "1",
    "--tile-id",
    "2",
    "--epoch-id",
    "3",
    "--band-id",
    "4",
    "--instrument-id",
    "5",
    "--filename",
    "mosaic_1.fits",
    "--target-plate-scale",
    "0.03",
]


def test_parser_recognises_create_mosaic_command():
    args = build_parser().parse_args(["create-mosaic", *MOSAIC_ARGS])
    assert args.command == "create-mosaic"
    assert args.filename == "mosaic_1.fits"
    assert args.target_plate_scale == 0.03


def test_main_routes_create_mosaic_to_cmd_create_mosaic(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_create_mosaic")
    main(["create-mosaic", *MOSAIC_ARGS])
    mock_cmd.assert_called_once()


def test_cmd_create_mosaic_calls_service_and_prints_ids(mocker, capsys):
    mocker.patch(
        "src.services.mosaic_service.create_mosaic",
        return_value=("task-xyz", 11),
    )
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_create_mosaic(
        argparse.Namespace(
            command="create-mosaic",
            project_id=1,
            tile_id=2,
            epoch_id=3,
            band_id=4,
            instrument_id=5,
            filename="mosaic_1.fits",
            target_plate_scale=0.03,
        )
    )

    out = capsys.readouterr().out
    assert "task-xyz" in out
    assert "11" in out


def test_parser_recognises_mosaic_status_command():
    args = build_parser().parse_args(["mosaic-status", "--id", "11"])
    assert args.command == "mosaic-status"
    assert args.id == 11


def test_main_routes_mosaic_status_to_cmd_mosaic_status(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_mosaic_status")
    main(["mosaic-status", "--id", "11"])
    mock_cmd.assert_called_once()


def test_cmd_mosaic_status_prints_table_for_found_mosaic(mocker, capsys):
    from src.db.models import Level3Mosaic

    fake_mosaic = Level3Mosaic(
        id=11,
        filename="mosaic_1.fits",
        target_plate_scale=0.03,
        status="pending",
        ra=10.5,
        decl=41.2,
    )
    mocker.patch("src.services.mosaic_service.get_mosaic", return_value=fake_mosaic)
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_mosaic_status(argparse.Namespace(command="mosaic-status", id=11))

    out = capsys.readouterr().out
    assert "11" in out
    assert "mosaic_1.fits" in out
    assert "10.5" in out
    # Status view is curated for readability -- no bare FK ids, no raw footprint.
    assert "footprint" not in out
    assert "instrument_id" not in out
    assert "tile_id" not in out


def test_cmd_mosaic_status_prints_error_for_missing_mosaic(mocker, capsys):
    mocker.patch("src.services.mosaic_service.get_mosaic", return_value=None)
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())

    cmd_mosaic_status(argparse.Namespace(command="mosaic-status", id=404))

    out = capsys.readouterr().out
    assert "404" in out
    assert "Error" in out


# ---------------------------------------------------------------------------
# populate-demo-project coordinator
# ---------------------------------------------------------------------------


def test_poll_until_terminal_returns_immediately_on_complete():
    assert (
        _poll_until_terminal(lambda: JobStatus.COMPLETE, "X", timeout_s=1.0)
        == JobStatus.COMPLETE
    )


def test_poll_until_terminal_returns_failed_status():
    assert (
        _poll_until_terminal(lambda: JobStatus.FAILED, "X", timeout_s=1.0)
        == JobStatus.FAILED
    )


def test_poll_until_terminal_raises_timeout_error_when_never_terminal():
    with pytest.raises(TimeoutError, match="did not reach a terminal state"):
        _poll_until_terminal(
            lambda: JobStatus.IN_PROCESS, "X", timeout_s=0.05, interval_s=0.01
        )


POPULATE_DEMO_ARGS = dict(
    command="populate-demo-project",
    project_name="Demo Project",
    user_id=1,
    s3_prefix="raw/",
    ra=10.0,
    decl=20.0,
    radius_deg=0.1,
    tile_side_arcmin=6.0,
    overlap_arcmin=0.0,
    band_id=2,
    instrument_id=3,
    peak_distance_thresh=5.0,
    target_plate_scale=0.03,
    ingest_timeout=5.0,
    mosaic_timeout=5.0,
)


def test_parser_recognises_populate_demo_project_command():
    args = build_parser().parse_args(
        [
            "populate-demo-project",
            "--project-name",
            "Demo Project",
            "--user-id",
            "1",
            "--s3-prefix",
            "raw/",
            "--ra",
            "10.0",
            "--decl",
            "20.0",
            "--radius-deg",
            "0.1",
            "--band-id",
            "2",
            "--instrument-id",
            "3",
        ]
    )
    assert args.command == "populate-demo-project"
    assert args.tile_side_arcmin == 6.0
    assert args.target_plate_scale == 0.03


def test_main_routes_populate_demo_project_to_cmd(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_populate_demo_project")
    main(
        [
            "populate-demo-project",
            "--project-name",
            "Demo Project",
            "--user-id",
            "1",
            "--s3-prefix",
            "raw/",
            "--ra",
            "10.0",
            "--decl",
            "20.0",
            "--radius-deg",
            "0.1",
            "--band-id",
            "2",
            "--instrument-id",
            "3",
        ]
    )
    mock_cmd.assert_called_once()


def _mock_populate_services(
    mocker,
    ingest_status=JobStatus.COMPLETE,
    mosaic_status=JobStatus.COMPLETE,
    tiles=None,
    epochs=None,
    best_tile_id=5,
):
    mocker.patch("src.db.session.SessionLocal", return_value=MagicMock())
    project = MagicMock(id=1, slug="demo-project")
    mocker.patch("src.services.project_service.create_project", return_value=project)
    mocker.patch(
        "src.services.ingest_service.create_ingest_batch",
        return_value=("ingest-task", 10),
    )
    mocker.patch(
        "src.services.ingest_service.get_ingest_batch",
        return_value=MagicMock(status=ingest_status),
    )
    mocker.patch(
        "src.services.tile_service.generate_tile_tessellation",
        return_value=[{"name": "Tile_1"}],
    )
    mocker.patch(
        "src.services.tile_service.create_tiles",
        return_value=tiles if tiles is not None else [MagicMock(id=5)],
    )
    mocker.patch(
        "src.services.tile_service.tile_with_most_calibrations",
        return_value=best_tile_id,
    )
    mocker.patch(
        "src.services.epoch_service.cluster_epochs", return_value=[{"start_mjd": 1}]
    )
    mocker.patch(
        "src.services.epoch_service.create_epochs",
        return_value=epochs if epochs is not None else [MagicMock(id=6)],
    )
    mocker.patch(
        "src.services.mosaic_service.create_mosaic",
        return_value=("mosaic-task", 20),
    )
    mocker.patch(
        "src.services.mosaic_service.get_mosaic",
        return_value=MagicMock(status=mosaic_status),
    )
    return project


def test_cmd_populate_demo_project_happy_path(mocker, capsys):
    _mock_populate_services(mocker)

    cmd_populate_demo_project(argparse.Namespace(**POPULATE_DEMO_ARGS))

    out = capsys.readouterr().out
    assert "Created project" in out
    assert "Ingest complete." in out
    assert "Created 1 tile(s)" in out
    assert "Created 1 epoch(s)" in out
    assert "Mosaic finished with status=complete" in out
    assert "Demo project population complete. project_id=1" in out


def test_cmd_populate_demo_project_aborts_on_ingest_failure(mocker, capsys):
    _mock_populate_services(mocker, ingest_status=JobStatus.FAILED)
    mock_create_tiles = mocker.patch("src.services.tile_service.create_tiles")

    cmd_populate_demo_project(argparse.Namespace(**POPULATE_DEMO_ARGS))

    out = capsys.readouterr().out
    assert "Ingest batch failed. Aborting." in out
    mock_create_tiles.assert_not_called()


def test_cmd_populate_demo_project_aborts_when_no_tiles_generated(mocker, capsys):
    _mock_populate_services(mocker, tiles=[])
    mock_cluster = mocker.patch("src.services.epoch_service.cluster_epochs")

    cmd_populate_demo_project(argparse.Namespace(**POPULATE_DEMO_ARGS))

    out = capsys.readouterr().out
    assert "No tiles generated" in out
    mock_cluster.assert_not_called()


def test_cmd_populate_demo_project_aborts_when_no_tile_overlaps_data(mocker, capsys):
    """A tessellated grid can produce tiles with zero real spatial overlap (edge
    cells) even when tiles themselves were generated -- must not silently proceed
    with an arbitrary empty tile."""
    _mock_populate_services(mocker, best_tile_id=None)
    mock_cluster = mocker.patch("src.services.epoch_service.cluster_epochs")

    cmd_populate_demo_project(argparse.Namespace(**POPULATE_DEMO_ARGS))

    out = capsys.readouterr().out
    assert "No tile in the tessellated region overlaps any ingested calibration" in out
    mock_cluster.assert_not_called()


def test_cmd_populate_demo_project_aborts_when_no_epochs_generated(mocker, capsys):
    _mock_populate_services(mocker, epochs=[])
    mock_create_mosaic = mocker.patch("src.services.mosaic_service.create_mosaic")

    cmd_populate_demo_project(argparse.Namespace(**POPULATE_DEMO_ARGS))

    out = capsys.readouterr().out
    assert "No epochs generated" in out
    mock_create_mosaic.assert_not_called()


def test_cmd_populate_demo_project_closes_session(mocker):
    _mock_populate_services(mocker)
    mock_session = MagicMock()
    mocker.patch("src.db.session.SessionLocal", return_value=mock_session)

    cmd_populate_demo_project(argparse.Namespace(**POPULATE_DEMO_ARGS))

    mock_session.close.assert_called_once()
