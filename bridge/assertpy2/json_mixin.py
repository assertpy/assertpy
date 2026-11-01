"""`assertpy.json_mixin` under its old name: importing this module hands out that module itself."""

import sys

import assertpy.json_mixin
from assertpy.json_mixin import *  # noqa: F403 - lets a type checker see the names

sys.modules[__name__] = assertpy.json_mixin
