import os
import sys

sys.path.insert(0, os.path.abspath(".."))

# Provide dummy values so modules that read env vars at import time don't
# crash during the Sphinx autodoc import phase. No real connections are made.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://sphinx:sphinx@localhost/sphinx")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

project = "Diffpype"
copyright = "2026, STScI"
author = "Dave Coulter"
release = "0.1"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
]

# Mock heavy external deps so RTD does not need the full scientific Python stack.
autodoc_mock_imports = [
    "celery",
    "fastapi",
    "psycopg2",
    "pydantic",
    "redis",
    "sqlalchemy",
    "starlette",
    "uvicorn",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
