"""Sphinx configuration for tl_elliptec's documentation (Read the Docs)."""
import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "tl_elliptec"
copyright = "2026, Matteo Michiardi"
author = "Matteo Michiardi"

try:
    import tl_elliptec

    release = tl_elliptec.__version__
except ImportError:
    release = "0.0.0"
version = release

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- autodoc -----------------------------------------------------------
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
napoleon_google_docstring = True
napoleon_numpy_docstring = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- HTML output ---------------------------------------------------------
html_theme = "furo"
html_static_path = ["_static"]
html_title = "tl_elliptec"

html_theme_options = {
    "source_repository": "https://github.com/TapyrLabs/tl_elliptec/",
    "source_branch": "main",
    "source_directory": "docs/",
}
