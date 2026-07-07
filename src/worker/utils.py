"""Utility functions for building subprocess-safe CLI command lists."""


def build_cli_command(executable: str, kwargs: dict) -> list[str]:
    """Flatten a dict of keyword arguments into a subprocess-safe command list."""
    cmd = [executable]
    for key, value in kwargs.items():
        cmd.extend([f"-{key}", str(value)])
    return cmd
