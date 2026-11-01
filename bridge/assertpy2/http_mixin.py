"""`assertpy.http_mixin` under its old name: importing this module hands out that module itself."""

import sys

import assertpy.http_mixin
from assertpy.http_mixin import *  # noqa: F403 - lets a type checker see the names

sys.modules[__name__] = assertpy.http_mixin
