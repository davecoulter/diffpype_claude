import os
import sys

sys.path.insert(0, os.path.abspath(".."))

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
