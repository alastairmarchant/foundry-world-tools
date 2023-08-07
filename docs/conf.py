"""Sphinx configuration."""
project = "Foundry World Tools"
author = "Alastair Marchant"
copyright = "2023, Alastair Marchant"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_click",
    "myst_parser",
]
autodoc_typehints = "description"
html_theme = "furo"
