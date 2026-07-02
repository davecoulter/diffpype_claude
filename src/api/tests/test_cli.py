import argparse

import pytest

from src.cli import build_parser, cmd_seed_db, main


def test_parser_recognises_seed_db_command():
    args = build_parser().parse_args(["seed-db"])
    assert args.command == "seed-db"


def test_missing_command_exits():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_main_routes_seed_db_to_cmd_seed_db(mocker):
    mock_cmd = mocker.patch("src.cli.cmd_seed_db")
    main(["seed-db"])
    mock_cmd.assert_called_once()


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
