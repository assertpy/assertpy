"""`assertpy.bytes_mixin` under its old name: importing this module hands out that module itself."""

import sys

import assertpy.bytes_mixin
from assertpy.bytes_mixin import *  # noqa: F403 - lets a type checker see the names

sys.modules[__name__] = assertpy.bytes_mixin
