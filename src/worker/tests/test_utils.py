from src.worker.utils import build_cli_command


def test_build_cli_command_returns_executable_only_for_empty_kwargs():
    assert build_cli_command("hotpants", {}) == ["hotpants"]


def test_build_cli_command_flattens_kwargs_with_hyphen_prefix():
    result = build_cli_command("hotpants", {"inim": "sci.fits", "c": "t"})
    assert result == ["hotpants", "-inim", "sci.fits", "-c", "t"]


def test_build_cli_command_converts_numeric_values_to_strings():
    result = build_cli_command("tool", {"threshold": 3.14, "nstars": 100})
    assert result == ["tool", "-threshold", "3.14", "-nstars", "100"]


def test_build_cli_command_preserves_insertion_order():
    result = build_cli_command("cmd", {"b": "2", "a": "1"})
    assert result == ["cmd", "-b", "2", "-a", "1"]
