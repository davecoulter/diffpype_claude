"""Unit tests for the DiffpypeAuthBackend authentication logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import bcrypt

from src.api.admin import DiffpypeAuthBackend, UserAdmin
from src.db.models import User

_VALID_PASSWORD = "testpassword"
_VALID_HASH = bcrypt.hashpw(_VALID_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode(
    "utf-8"
)


def _make_backend():
    return DiffpypeAuthBackend(secret_key="test-secret")


def _make_request(form_data: dict, session: dict | None = None):
    request = MagicMock()
    request.form = AsyncMock(return_value=form_data)
    request.session = session if session is not None else {}
    return request


def test_login_succeeds_with_valid_credentials(mocker):
    fake_user = MagicMock(spec=User, hashed_password=_VALID_HASH, is_active=True)
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.one_or_none.return_value = (
        fake_user
    )
    mocker.patch("src.api.admin.SessionLocal", return_value=mock_db)

    session = {}
    request = _make_request(
        {"username": "sysadmin", "password": _VALID_PASSWORD}, session
    )
    result = asyncio.run(_make_backend().login(request))

    assert result is True
    assert session.get("authenticated") is True


def test_login_fails_with_wrong_password(mocker):
    fake_user = MagicMock(spec=User, hashed_password=_VALID_HASH, is_active=True)
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.one_or_none.return_value = (
        fake_user
    )
    mocker.patch("src.api.admin.SessionLocal", return_value=mock_db)

    session = {}
    request = _make_request(
        {"username": "sysadmin", "password": "wrongpassword"}, session
    )
    result = asyncio.run(_make_backend().login(request))

    assert result is False
    assert "authenticated" not in session


def test_login_fails_gracefully_when_hash_is_invalid(mocker):
    fake_user = MagicMock(
        spec=User, hashed_password="not-a-bcrypt-hash", is_active=True
    )
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.one_or_none.return_value = (
        fake_user
    )
    mocker.patch("src.api.admin.SessionLocal", return_value=mock_db)

    session = {}
    request = _make_request({"username": "sysadmin", "password": "anything"}, session)
    result = asyncio.run(_make_backend().login(request))

    assert result is False
    assert "authenticated" not in session


def test_login_fails_when_user_not_found(mocker):
    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.one_or_none.return_value = None
    mocker.patch("src.api.admin.SessionLocal", return_value=mock_db)

    session = {}
    request = _make_request({"username": "nobody", "password": "anything"}, session)
    result = asyncio.run(_make_backend().login(request))

    assert result is False
    assert "authenticated" not in session


def test_authenticate_returns_true_when_session_is_valid():
    request = _make_request({}, session={"authenticated": True})
    result = asyncio.run(_make_backend().authenticate(request))
    assert result is True


def test_authenticate_returns_false_when_session_is_empty():
    request = _make_request({}, session={})
    result = asyncio.run(_make_backend().authenticate(request))
    assert result is False


def test_on_model_change_hashes_plain_text_password():
    data = {"hashed_password": "plaintext_password"}
    result = asyncio.run(
        UserAdmin().on_model_change(data, MagicMock(), True, MagicMock())
    )
    assert result is None
    stored = data["hashed_password"]
    assert stored != "plaintext_password"
    assert bcrypt.checkpw(b"plaintext_password", stored.encode("utf-8"))


def test_on_model_change_skips_empty_password():
    data = {"hashed_password": ""}
    asyncio.run(UserAdmin().on_model_change(data, MagicMock(), True, MagicMock()))
    assert data["hashed_password"] == ""


def test_logout_clears_session():
    session = {"authenticated": True}
    request = _make_request({}, session=session)
    result = asyncio.run(_make_backend().logout(request))

    assert result is True
    assert session == {}
