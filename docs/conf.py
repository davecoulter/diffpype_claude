import os
import sys

sys.path.insert(0, os.path.abspath(".."))

# Provide dummy values so modules that read env vars at import time don't
# crash during the Sphinx autodoc import phase. No real connections are made.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://sphinx:sphinx@localhost/sphinx")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ADMIN_USER", "sysadmin")
os.environ.setdefault("ADMIN_PASSWORD", "sphinx-placeholder")
os.environ.setdefault("ADMIN_SECRET_KEY", "sphinx-placeholder-secret")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

project = "Diffpype"
copyright = "2026, STScI"
author = "Dave Coulter"
release = "0.1"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "myst_parser",
]

# The architecture ADRs intentionally start at an H5/H6 heading convention for
# their in-repo Markdown rendering. Suppress only MyST's heading-level lint so a
# ``-W`` build stays meaningful for every other warning class (broken links,
# missing toctree references, autodoc import errors, etc.).
suppress_warnings = ["myst.header"]

# Mock heavy external deps so RTD does not need the full scientific Python stack.
autodoc_mock_imports = [
    "bcrypt",
    "celery",
    "fastapi",
    "itsdangerous",
    "psycopg2",
    "pydantic",
    "pydantic_settings",
    "redis",
    "sqladmin",
    "sqlalchemy",
    "src.api.admin",
    "starlette",
    "structlog",
    "uvicorn",
]

# prd.md is the Product Requirements Document, not part of the ADR wiki; exclude
# it from the Sphinx source tree so MyST does not flag it as an orphaned page.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "prd.md"]

html_theme = "sphinx_rtd_theme"
