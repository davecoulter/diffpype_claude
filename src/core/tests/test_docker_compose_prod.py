"""Regression test guarding against docker-compose.prod.yml drifting from the ghcr.io image names ci.yml actually publishes."""

from pathlib import Path

import pytest

COMPOSE_PATH = Path(__file__).resolve().parents[3] / "docker-compose.prod.yml"
EXPECTED_IMAGE_PREFIX = "ghcr.io/davecoulter/diffpype_claude-"

if not COMPOSE_PATH.exists():
    pytest.skip(
        "docker-compose.prod.yml is host-only orchestration config, not copied into the "
        "api image or bind-mounted in dev — only reachable when pytest runs against the "
        "full repo checkout (host or CI), not inside the api container.",
        allow_module_level=True,
    )


def test_prod_compose_images_match_ghcr_package_names():
    """docker-compose.prod.yml must reference the same image names ci.yml pushes to ghcr.io."""
    content = COMPOSE_PATH.read_text()
    assert content.count(f"image: {EXPECTED_IMAGE_PREFIX}api:") == 1
    assert content.count(f"image: {EXPECTED_IMAGE_PREFIX}worker:") == 2
    assert content.count(f"image: {EXPECTED_IMAGE_PREFIX}db:") == 1


def test_prod_compose_db_does_not_build_locally():
    """db must pull a versioned ghcr.io image in prod, not build from a local Dockerfile context."""
    content = COMPOSE_PATH.read_text()
    assert "dockerfile: docker/db.Dockerfile" not in content
