"""`assertpy.errors` under its old name: importing this module hands out that module itself."""

import sys

import assertpy.errors
from assertpy.errors import *  # noqa: F403 - lets a type checker see the names

sys.modules[__name__] = assertpy.errors
