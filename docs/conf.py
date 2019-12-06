# fixup path
import os
import sys
sys.path.insert(0, os.path.abspath('..'))
print('SYS.PATH=', sys.path)

# proj info
project = 'assertpy'
copyright = '2014-2019 Activision Publishing Inc'
author = 'Activision'

# extensions (for Google-style doc strings)
extensions = [
    'sphinx.ext.autodoc',
    'sphinxcontrib.napoleon'
]

exclude_patterns = ['build', '.DS_Store']

html_theme = 'sphinx_rtd_theme'
