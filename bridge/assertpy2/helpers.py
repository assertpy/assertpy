"""`assertpy.helpers` under its old name: importing this module hands out that module itself."""

import sys

import assertpy.helpers
from assertpy.helpers import *  # noqa: F403 - lets a type checker see the names

sys.modules[__name__] = assertpy.helpers
