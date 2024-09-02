import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join('..','..','src')))


# ------Project information --------
project = 'fusion-tools'
author = 'Sam Border'
version = release = '0.0.5'

# ------ Configuration -----------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "spinx.ext.converage"
]

templates_path = ["_templates"]

exclude_patterns = []

html_theme = 'alabaster'

html_static_path = ["_static"]