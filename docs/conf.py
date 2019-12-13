# fixup path
import os
import sys
sys.path.insert(0, os.path.abspath('..'))
print('SYS.PATH=', sys.path)

# proj info
project = 'assertpy'
copyright = '2015-2019 Activision Publishing, Inc.'
author = 'Activision'

# extensions (for Google-style doc strings)
extensions = [
    'sphinx.ext.autodoc',
    'sphinxcontrib.napoleon'
]

templates_path = ['templates']

exclude_patterns = ['build', '.DS_Store']

# html_theme = 'sphinx_rtd_theme'

add_module_names = False
