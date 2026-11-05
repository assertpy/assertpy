"""The types the snapshot files in `snapshot_files_2_35/` were written with, by assertpy 2.35.0 from PyPI.

A snapshot names the class of an enum member or of an instance by module and name, and reads it back only from a
module already imported, so these live in a module of their own that both the writer and the test import.
"""

import datetime
import enum
import typing


class Colour(enum.Enum):
    RED = (255, 0, 0)


class Future(enum.Enum):
    LATER = {"__type__": "future", "__data__": None, "when": datetime.date(2026, 1, 2)}  # noqa: RUF012  # an enum member, not a class attribute


class Shaped(enum.Enum):
    TAGGED = {"__type__": "tuple", "__data__": [1, 2]}  # noqa: RUF012  # an enum member, not a class attribute
    PAIR = (1, 2)


class Nested(enum.Enum):
    ONLY = {  # noqa: RUF012  # an enum member, not a class attribute
        "enum": {
            "__type__": "enum",
            "__class__": "Gone",
            "__module__": "no.such",
            "__data__": 1,
            "when": datetime.date(2026, 1, 2),
        },
        "instance": {
            "__type__": "instance",
            "__class__": "Gone",
            "__module__": "no.such",
            "__data__": {},
            "when": datetime.date(2026, 1, 3),
        },
    }


class Holder:
    def __init__(self, pair):
        self.pair = pair

    def __eq__(self, other):
        return type(other) is Holder and other.pair == self.pair

    __hash__ = None


class Point(typing.NamedTuple):
    x: int
    y: int


class Box:
    def __init__(self, content):
        self.content = content

    def __eq__(self, other):
        return type(other) is Box and other.content == self.content

    __hash__ = None
