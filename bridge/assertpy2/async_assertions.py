"""`assertpy.async_assertions` under its old name: importing this module hands out that module itself."""

import sys

import assertpy.async_assertions
from assertpy.async_assertions import *  # noqa: F403 - lets a type checker see the names

sys.modules[__name__] = assertpy.async_assertions
