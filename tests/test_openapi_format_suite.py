"""What `conforms_to_openapi` checks of its own, held to the official JSON Schema test suite.

The files under ``tests/data/json_schema_test_suite`` are ``tests/draft2020-12/optional/format`` of
json-schema-org/JSON-Schema-Test-Suite at revision ``5b0ee1613e45fcc2bddac00e07c19cd49b00d8a8``, and
``multipleOf.json`` of ``tests/draft2020-12`` beside them, unchanged, with the licence of that repository.
They are cases written by other hands than this library's: a test written with the code pins the reading of
whoever wrote both.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any

import pytest

from assertpy import assert_that
from tests.optional import needs

needs("jsonschema")
needs("idna")

_SUITE = pathlib.Path(__file__).resolve().parent / "data" / "json_schema_test_suite"
_FORMATS = ("date", "date-time", "duration", "email", "hostname", "time", "uri")


def _cases(formats: tuple[str, ...]) -> list[Any]:
    found = []
    for form in formats:
        for group in json.loads((_SUITE / f"{form}.json").read_text(encoding="utf-8")):
            found.extend(
                pytest.param(group["schema"], case["data"], case["valid"], id=f"{form}: {case['description']}")
                for case in group["tests"]
            )
    return found


_A_LABEL = re.compile(r"(?i)(?<![^.])xn--")
"""A label the dialect of OpenAPI 3.1 holds to IDNA, and the one of 3.0 reads by its letters."""

_CONTENT = {
    "date": "b8e7e8448fdd9d6ff1674bae652e966f5b7bd2bfe2a98b04ba3cae1ab2d73d68",
    "date-time": "a33151e215521153f9f463be0d28c5b422d376572169e61b2425a634b008202c",
    "duration": "bba1dbed0c41c16eabc0a1ab6d26d58a6fdd6b9624358bc9583fcceccfe41a91",
    "email": "5354bb2971299ef6edd36c65f86ac66f50cd25cd1a770c9199be05bb6ec5866d",
    "hostname": "d621bd19097237f36b6b297109ff651b85603633f7461b803dcdc052b463a206",
    "multipleOf": "4af4e2bcf6c098695e9dbdcbb33ae5ee8139e3100dcb03a3ff7d68156f61bc06",
    "time": "dc9491c5e982465f09dcb47be21c98940abceee1882dfbdb4be7f87d7546701e",
    "uri": "68260e635545d2fa2d3a6afb9e0cb6dec688aa7477b375b0d52a2f2d9d67949f",
}
"""SHA-256 of each file read as JSON and written back with sorted keys, so a line ending changes nothing."""


def _took(schema: Any, value: object, version: str) -> bool:
    response = {"content": {"application/json": {"schema": schema}}}
    spec = {"openapi": version, "paths": {"/x": {"get": {"responses": {"200": response}}}}}
    return assert_that(value).check().conforms_to_openapi(spec, "/x", "get").passed


@pytest.mark.parametrize(("schema", "value", "valid"), _cases(_FORMATS))
def test_a_case_of_the_suite_gets_the_verdict_the_suite_gives_it(schema, value, valid):
    assert_that(_took(schema, value, "3.1.0")).is_equal_to(valid)


@pytest.mark.parametrize(("schema", "value", "valid"), _cases(_FORMATS))
def test_under_three_zero_a_case_gets_that_verdict_but_for_an_a_label(schema, value, valid):
    """A format is checked alike in both dialects, and the ``$schema`` of a case changes nothing, with one
    difference that is the dialects' own: the JSON Schema of 3.0 has a host name as its syntax, so a label
    that opens ``xn--`` and is no A-label is a host name there."""
    by_its_letters = schema.get("format") == "hostname" and isinstance(value, str) and _A_LABEL.search(value)
    assert_that(_took(schema, value, "3.0.3")).is_equal_to(True if by_its_letters and not valid else valid)


def test_the_cases_three_zero_reads_otherwise_are_the_a_labels_of_the_suite():
    apart = [
        case.values[1]
        for case in _cases(("hostname",))
        if not case.values[2] and isinstance(case.values[1], str) and _A_LABEL.search(case.values[1])
    ]
    assert_that(len(apart)).is_equal_to(23)
    for value in apart:
        assert_that(_took({"format": "hostname"}, value, "3.0.3")).described_as(value).is_true()
        assert_that(_took({"format": "hostname"}, value, "3.1.0")).described_as(value).is_false()


@pytest.mark.parametrize("version", ["3.0.3", "3.1.0"])
@pytest.mark.parametrize(("schema", "value", "valid"), _cases(("multipleOf",)))
def test_a_case_of_multiple_of_gets_the_verdict_the_suite_gives_it(schema, value, valid, version):
    assert_that(_took(schema, value, version)).is_equal_to(valid)


def test_the_files_are_the_ones_of_the_revision_named():
    """Held by content: a case edited to agree with the library would keep every count as it was."""
    read = {name: json.loads((_SUITE / f"{name}.json").read_text(encoding="utf-8")) for name in _CONTENT}
    counted = {name: sum(len(group["tests"]) for group in groups) for name, groups in read.items()}
    assert_that(counted).is_equal_to(
        {
            "date": 81,
            "date-time": 43,
            "duration": 52,
            "email": 71,
            "hostname": 64,
            "multipleOf": 11,
            "time": 55,
            "uri": 47,
        }
    )
    content = {
        name: hashlib.sha256(json.dumps(groups, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()
        for name, groups in read.items()
    }
    assert_that(content).is_equal_to(_CONTENT)
    licence = " ".join((_SUITE / "LICENSE").read_text(encoding="utf-8").split())
    assert_that(hashlib.sha256(licence.encode("utf-8")).hexdigest()).is_equal_to(
        "f2b5ac6871259bee19b75412622d4f80f634e7c1d76aee0b9d28ee84d35e6825"
    )
