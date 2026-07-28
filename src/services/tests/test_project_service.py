from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.db.models import Project
from src.services.project_service import create_project


def test_create_project_generates_slug_from_name(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 1)

    project = create_project(mock_db, "My First Survey!", "desc", user_id=1)

    assert project.slug == "my-first-survey"
    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, Project)
    assert added.name == "My First Survey!"
    assert added.description == "desc"
    assert added.user_id == 1
    mock_db.commit.assert_called_once()


def test_create_project_raises_value_error_on_slug_collision():
    mock_db = MagicMock()
    mock_db.commit.side_effect = IntegrityError("stmt", "params", Exception("orig"))

    with pytest.raises(ValueError, match="already exists"):
        create_project(mock_db, "Duplicate Name", None, user_id=1)

    mock_db.rollback.assert_called_once()
