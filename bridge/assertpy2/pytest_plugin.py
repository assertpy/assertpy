"""`assertpy.pytest_plugin` under its old name: importing this module hands out that module itself."""

import sys

import assertpy.pytest_plugin
from assertpy.pytest_plugin import *  # noqa: F403 - lets a type checker see the names

sys.modules[__name__] = assertpy.pytest_plugin
