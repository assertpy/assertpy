"""`assertpy.behave_matchers` under its old name: importing this module hands out that module itself."""

import sys

import assertpy.behave_matchers
from assertpy.behave_matchers import *  # noqa: F403 - lets a type checker see the names

sys.modules[__name__] = assertpy.behave_matchers
