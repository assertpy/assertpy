"""The formats `conforms_to_openapi` checks, each held to the document that defines it.

jsonschema checks `date-time` only beside a package this library does not install, and knows nothing of
OpenAPI's `int32` and `int64`, so ``"yesterday"`` passed for a moment and ``2**40`` for an `int32`.  The
moments here are the examples and the grammar of RFC 3339, and the bounds are the signed ranges.
"""

from __future__ import annotations

import re
import subprocess
import sys
import typing
from typing import Any
from unittest.mock import patch

import pytest

from assertpy import AssertionFailure, assert_that, json_mixin
from tests.format_corpus import mailboxes, uris

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema not installed")


def _spec(version: str, schema: dict[str, Any]) -> dict[str, Any]:
    wrapped = {"type": "object", "properties": {"v": schema}}
    if version == "2.0":
        return {"swagger": "2.0", "paths": {"/orders": {"get": {"responses": {"200": {"schema": wrapped}}}}}}
    return {
        "openapi": version,
        "paths": {"/orders": {"get": {"responses": {"200": {"content": {"application/json": {"schema": wrapped}}}}}}},
    }


def _conforms(value: object, schema: dict[str, Any], version: str = "3.0.3") -> bool:
    try:
        assert_that({"v": value}).conforms_to_openapi(_spec(version, schema), "/orders", "get")
    except AssertionFailure:
        return False
    return True


_MOMENT = {"type": "string", "format": "date-time"}


class TestADateTimeIsWrittenAsRfc3339WritesIt:
    @pytest.mark.parametrize(
        "moment",
        [
            "1985-04-12T23:20:50.52Z",
            "1996-12-19T16:39:57-08:00",
            "1990-12-31T23:59:60Z",
            "1990-12-31T15:59:60-08:00",
            "1937-01-01T12:00:27.87+00:20",
            "1985-04-12t23:20:50z",
            "2026-02-28T00:00:00+23:59",
            "2024-02-29T10:00:00.123456789012Z",
            "2000-02-29T00:00:00Z",
            "0000-02-29T00:00:00Z",
        ],
    )
    def test_a_moment_the_rfc_writes_passes(self, moment):
        assert_that(_conforms(moment, _MOMENT)).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "yesterday",
            "2026-13-45T99:99",
            "2026-02-30T10:00:00Z",
            "2026-02-29T10:00:00Z",
            "1900-02-29T10:00:00Z",
            "2026-13-01T10:00:00Z",
            "2026-00-10T10:00:00Z",
            "2026-01-00T10:00:00Z",
            "2026-04-31T10:00:00Z",
            "2026-01-01 10:00:00Z",
            "2026-01-01T10:00:00",
            "2026-01-01T24:00:00Z",
            "2026-01-01T10:60:00Z",
            "2026-01-01T10:00:61Z",
            "2026-01-01T10:00:00+24:00",
            "2026-01-01T10:00:00+10:60",
            "2026-01-01T10:00:00Z ",
            "2026-01-01T10:00:00.Z",
            "2026-01-01T10:00Z",
            "٢٠٢٦-01-01T10:00:00Z",
            "",
        ],
    )
    def test_a_text_that_is_none_fails(self, text):
        assert_that(_conforms(text, _MOMENT)).is_false()

    @pytest.mark.parametrize(
        "moment",
        [
            "1990-12-31T23:59:60Z",
            "1990-12-31T23:59:60.5z",
            "1990-12-31T15:59:60-08:00",
            "2026-07-01T08:59:60+09:00",
            "2026-06-30T23:59:60+00:00",
            "2026-06-30T23:59:60-00:00",
            "2026-06-30T00:00:60-23:59",
            "2026-07-01T23:58:60+23:59",
            "2026-02-28T23:59:60Z",
            "2024-02-29T23:59:60Z",
        ],
    )
    def test_a_second_of_sixty_passes_in_the_last_minute_of_a_month_in_utc(self, moment):
        assert_that(_conforms(moment, _MOMENT)).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "2026-01-01T10:00:60Z",
            "2026-06-29T23:59:60Z",
            "2026-06-30T23:58:60Z",
            "2026-06-30T23:59:60+01:00",
            "2026-06-30T23:59:60-00:01",
            "2026-06-30T15:59:60+08:00",
            "2026-07-02T08:59:60+09:00",
            "2026-07-01T08:59:60-09:00",
            "2026-06-30T08:59:60+09:00",
            "2024-02-28T23:59:60Z",
            "2026-06-31T23:59:60Z",
            "2026-06-30T23:59:61Z",
        ],
    )
    def test_a_second_of_sixty_fails_anywhere_else(self, text):
        assert_that(_conforms(text, _MOMENT)).is_false()

    @pytest.mark.parametrize("version", ["2.0", "3.0.3", "3.1.0", "3.2.0"])
    def test_in_every_dialect_the_assertion_reads(self, version):
        assert_that(_conforms("yesterday", _MOMENT, version)).is_false()
        assert_that(_conforms("1985-04-12T23:20:50.52Z", _MOMENT, version)).is_true()

    def test_a_text_of_a_class_of_its_own_is_a_text(self):
        named = type("Named", (str,), {})
        assert_that(_conforms(named("yesterday"), _MOMENT)).is_false()
        assert_that(_conforms(named("1985-04-12T23:20:50.52Z"), _MOMENT)).is_true()

    def test_what_is_no_text_is_the_type_keywords_to_judge(self):
        assert_that(_conforms(5, {"format": "date-time"})).is_true()
        assert_that(_conforms(None, {"format": "date-time"})).is_true()
        assert_that(_conforms(5, _MOMENT)).is_false()

    def test_a_check_jsonschema_brings_of_its_own_does_not_take_its_place(self, monkeypatch):
        """Beside the package that gives jsonschema a `date-time` check, a text still gets the verdict it gets here."""
        asked = []

        def theirs(value: object) -> bool:
            asked.append(value)
            return True

        monkeypatch.setitem(jsonschema.FormatChecker.checkers, "date-time", (theirs, ()))
        assert_that(_conforms("yesterday", _MOMENT)).is_false()
        assert_that(_conforms("0000-02-29T23:59:60Z", _MOMENT)).is_true()
        assert_that(asked).is_empty()


class TestAnIntegerFormatIsItsSignedRange:
    @pytest.mark.parametrize(
        ("bits", "value", "fits"),
        [
            (32, 2**31 - 1, True),
            (32, 2**31, False),
            (32, -(2**31), True),
            (32, -(2**31) - 1, False),
            (32, 2**40, False),
            (32, 0, True),
            (64, 2**63 - 1, True),
            (64, 2**63, False),
            (64, -(2**63), True),
            (64, -(2**63) - 1, False),
            (64, 2**70, False),
            (64, 2**40, True),
        ],
    )
    def test_a_whole_number_is_held_to_the_range(self, bits, value, fits):
        schema = {"type": "integer", "format": f"int{bits}"}
        assert_that(_conforms(value, schema)).is_equal_to(fits)
        assert_that(_conforms(value, schema, "3.1.0")).is_equal_to(fits)

    def test_a_float_that_holds_a_whole_number_is_one(self):
        assert_that(_conforms(2.0**31, {"type": "number", "format": "int32"})).is_false()
        assert_that(_conforms(5.0, {"type": "number", "format": "int32"})).is_true()
        assert_that(_conforms(5.5, {"type": "number", "format": "int32"})).is_true()

    def test_a_whole_number_of_a_class_of_its_own_is_one(self):
        counted = type("Counted", (int,), {})
        measured = type("Measured", (float,), {})
        assert_that(_conforms(counted(2**40), {"format": "int32"})).is_false()
        assert_that(_conforms(counted(7), {"format": "int32"})).is_true()
        assert_that(_conforms(measured(2.0**40), {"format": "int32"})).is_false()

    def test_a_number_that_answers_its_own_comparisons_is_read_by_what_it_holds(self):
        agreeing = type("Agreeing", (int,), {"__le__": lambda self, other: True, "__ge__": lambda self, other: True})
        refusing = type("Refusing", (int,), {"__le__": lambda self, other: False, "__ge__": lambda self, other: False})
        rounded = type("Rounded", (float,), {"is_integer": lambda self: False, "__le__": lambda self, other: True})
        assert_that(_conforms(agreeing(2**40), {"format": "int32"})).is_false()
        assert_that(_conforms(refusing(7), {"format": "int32"})).is_true()
        assert_that(_conforms(rounded(2.0**40), {"format": "int32"})).is_false()

    def test_what_is_no_number_is_the_type_keywords_to_judge(self):
        assert_that(_conforms("5", {"format": "int32"})).is_true()
        assert_that(_conforms("5", {"type": "integer", "format": "int32"})).is_false()

    def test_the_failure_names_the_place_and_the_format(self):
        outcome = (
            assert_that({"v": 2**40})
            .check()
            .conforms_to_openapi(_spec("3.0.3", {"type": "integer", "format": "int32"}), "/orders", "get")
        )
        assert_that(outcome.passed).is_false()
        entries = outcome.diff.entries
        assert_that([(entry.path, entry.actual) for entry in entries]).is_equal_to([("$.v", 2**40)])
        assert_that(entries[0].expected).contains("int32")


class TestWhatJsonschemaCheckedAlreadyIsCheckedStill:
    @pytest.mark.parametrize(
        ("form", "good", "bad"),
        [
            ("date", "2026-02-28", "2026-13-45"),
            ("ipv4", "10.0.0.1", "10.0.0.256"),
            ("uuid", "123e4567-e89b-12d3-a456-426614174000", "not-a-uuid"),
        ],
    )
    def test_each_keeps_its_check(self, form, good, bad):
        schema = {"type": "string", "format": form}
        assert_that(_conforms(good, schema, "3.1.0")).is_true()
        assert_that(_conforms(bad, schema, "3.1.0")).is_false()


def _text_of(form: str) -> dict[str, Any]:
    return {"type": "string", "format": form}


class TestAUriIsWrittenAsRfc3986WritesIt:
    """The grammar is appendix A of RFC 3986, and the first eight texts are the examples of its section 1.1.2."""

    @pytest.mark.parametrize(
        "uri",
        [
            "ftp://ftp.is.co.za/rfc/rfc1808.txt",
            "http://www.ietf.org/rfc/rfc2396.txt",
            "ldap://[2001:db8::7]/c=GB?objectClass?one",
            "mailto:John.Doe@example.com",
            "news:comp.infosystems.www.servers.unix",
            "tel:+1-816-555-1212",
            "telnet://192.0.2.16:80/",
            "urn:oasis:names:specification:docbook:dtd:xml:4.1.2",
            "a:",
            "a+b-c.d:x",
            "http://",
            "http:///path",
            "http://example.com:",
            "http://u:p@example.com:8080/a/b;c=1?q=1&r=/?#frag/?",
            "http://[::1]",
            "http://[::ffff:192.0.2.1]/",
            "http://[v7.fe80::a+en1]/",
            "http://999.999.999.999/",
            "http://ex%41mple.com/%7Ea",
            "file:///etc/hosts",
            "x:/",
            "x:/a",
            "x:a/b",
            "x:a:b@c",
            "x:?q",
            "x:#f",
            "x:/%41",
            "x:%41",
            "x:?%41",
            "x:#%41",
            "http://u%41@example.com/",
            "http://example.com/-._~!$&'()*+,;=:@",
        ],
    )
    def test_a_uri_passes(self, uri):
        assert_that(_conforms(uri, _text_of("uri"))).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "example.com",
            "/orders/7",
            "//example.com/x",
            "1http://x",
            "ht_tp://x",
            ":x",
            "http://exa mple.com",
            "http://example.com/a b",
            "http://example.com/\u00e9",
            "http://example.com/%4",
            "http://example.com/%zz",
            "http://example.com/%",
            "http://u%4@example.com/",
            "http://ex%4/",
            "x:/%4",
            "x:%4",
            "x:?%4",
            "x:#%4",
            "http://example.com:80a/",
            "http://[::1",
            "http://::1]/",
            "http://[::1]x/",
            "http://[fe80::1%25en0]/",
            "http://[::ffff:01.2.3.4]/",
            "http://[1]",
            "http://[v.x]/",
            "http://[vz.x]/",
            "http://[v7.]/",
            "http://u@v@example.com/",
            "http://example.com/a\\b",
            "http://example.com/<x>",
            "http://example.com/a^b",
            "http://example.com/\n",
            "\nhttp://example.com/",
            "x:[",
            "http:/[::1]",
            "x:a#b#c",
            "x:?a#b[",
            "x:?[",
        ],
    )
    def test_a_text_that_is_none_fails(self, text):
        assert_that(_conforms(text, _text_of("uri"))).is_false()


def _abnf_of_rfc_3986() -> str:
    """Appendix A of RFC 3986 written out production by production: a second writing of the pattern checked.

    The pattern of the library writes a path as one run and asks `ipaddress` for an address.  This one keeps
    the segments, the percent-encoded triplet as an alternative of its own, and the nine forms of an
    ``IPv6address``.
    """
    unreserved, sub_delims, pct_encoded = r"[A-Za-z0-9\-._~]", "[!$&'()*+,;=]", "%[0-9A-Fa-f]{2}"
    pchar = f"(?:{unreserved}|{pct_encoded}|{sub_delims}|[:@])"
    segment, segment_nz = f"{pchar}*", f"{pchar}+"
    dec_octet = "(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9][0-9]|[0-9])"
    ipv4 = rf"{dec_octet}\.{dec_octet}\.{dec_octet}\.{dec_octet}"
    h16 = "[0-9A-Fa-f]{1,4}"
    ls32 = f"(?:{h16}:{h16}|{ipv4})"
    ipv6 = "|".join(
        [
            f"(?:{h16}:){{6}}{ls32}",
            f"::(?:{h16}:){{5}}{ls32}",
            f"(?:{h16})?::(?:{h16}:){{4}}{ls32}",
            f"(?:(?:{h16}:){{0,1}}{h16})?::(?:{h16}:){{3}}{ls32}",
            f"(?:(?:{h16}:){{0,2}}{h16})?::(?:{h16}:){{2}}{ls32}",
            f"(?:(?:{h16}:){{0,3}}{h16})?::{h16}:{ls32}",
            f"(?:(?:{h16}:){{0,4}}{h16})?::{ls32}",
            f"(?:(?:{h16}:){{0,5}}{h16})?::{h16}",
            f"(?:(?:{h16}:){{0,6}}{h16})?::",
        ]
    )
    ip_future = rf"[vV][0-9A-Fa-f]+\.(?:{unreserved}|{sub_delims}|:)+"
    host = rf"(?:\[(?:{ipv6}|{ip_future})\]|{ipv4}|(?:{unreserved}|{pct_encoded}|{sub_delims})*)"
    authority = f"(?:(?:{unreserved}|{pct_encoded}|{sub_delims}|:)*@)?{host}(?::[0-9]*)?"
    hier_part = f"(?://{authority}(?:/{segment})*|/(?:{segment_nz}(?:/{segment})*)?|{segment_nz}(?:/{segment})*|)"
    return rf"[A-Za-z][A-Za-z0-9+\-.]*:{hier_part}(?:\?(?:{pchar}|[/?])*)?(?:#(?:{pchar}|[/?])*)?"


class TestTheUriCheckIsTheGrammarWrittenOut:
    def test_over_every_text_of_the_corpus_the_two_writings_agree(self):
        written_out = re.compile(_abnf_of_rfc_3986())
        took = 0
        for text in sorted(set(uris())):
            by_the_grammar = written_out.fullmatch(text) is not None
            took += by_the_grammar
            assert_that(json_mixin._is_uri(text)).described_as(f"{text!r} against the ABNF").is_equal_to(by_the_grammar)
        assert_that(took).is_greater_than(1000)


class TestAnAddressInBracketsIsTheIPv6AddressOfRfc3986:
    """The address is asked of `ipaddress`, whose reading is the interpreter's: held here on every one."""

    @pytest.mark.parametrize(
        "address",
        [
            "::",
            "::1",
            "1::",
            "1:2:3:4:5:6:7:8",
            "1:2:3:4:5:6:7::",
            "::2:3:4:5:6:7:8",
            "1::3:4:5:6:7:8",
            "2001:DB8::7",
            "0001:0002::",
            "::1.2.3.4",
            "::ffff:255.255.255.255",
            "1:2:3:4:5:6:1.2.3.4",
            "1:2:3:4:5::1.2.3.4",
        ],
    )
    def test_an_address_passes(self, address):
        assert_that(_conforms(f"http://[{address}]/", _text_of("uri"))).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "",
            ":",
            ":::",
            ":1",
            "1:",
            "1",
            "1:2:3:4:5:6:7",
            "1:2:3:4:5:6:7:8:9",
            "1:2:3:4::5:6:7:8",
            "1::2::3",
            "12345::",
            "::g",
            "1.2.3.4",
            "::1.2.3",
            "::1.2.3.4.5",
            "::256.1.1.1",
            "::01.2.3.4",
            "::1.2.3.04",
            "::1.2.3.4:5",
            "1:2:3:4:5:6:7:1.2.3.4",
            "::1%25en0",
            "::1 ",
        ],
    )
    def test_a_text_that_is_none_fails(self, text):
        assert_that(_conforms(f"http://[{text}]/", _text_of("uri"))).is_false()


class TestAHostnameIsWrittenAsRfc1123WritesIt:
    @pytest.mark.parametrize(
        "name",
        [
            "example.com",
            "localhost",
            "a",
            "A1",
            "1host",
            "1.2.3.4",
            "a-b.c-d",
            "a--b",
            "xn--nxasmq6b",
            "x" * 63,
            ".".join(["x" * 63, "x" * 63, "x" * 63, "x" * 61]),
        ],
        ids=lambda name: name if len(name) < 20 else f"{len(name)} characters",
    )
    def test_a_host_name_passes(self, name):
        assert_that(_conforms(name, _text_of("hostname"))).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "",
            ".",
            "a.",
            ".a",
            "a..b",
            "-a",
            "a-",
            "a.-b",
            "a-.b",
            "a.b-",
            "xn--",
            "xn--abc-",
            "a_b",
            "a b",
            "exa\u00e9mple",
            "a\n",
            "a/b",
            "a:80",
            "[::1]",
            "x" * 64,
            "a." + "x" * 64,
            ".".join(["x" * 63, "x" * 63, "x" * 63, "x" * 62]),
        ],
        ids=lambda text: ascii(text) if len(text) < 20 else f"{len(text)} characters",
    )
    def test_a_text_that_is_none_fails(self, text):
        assert_that(_conforms(text, _text_of("hostname"))).is_false()

    def test_the_length_is_the_texts_and_not_what_its_class_says(self):
        class Short(str):
            __slots__ = ()

            def __len__(self) -> int:
                return 1

        assert_that(_conforms(Short(".".join(["x" * 59] * 5)), _text_of("hostname"))).is_false()
        assert_that(_conforms(Short("example.com"), _text_of("hostname"))).is_true()

    @pytest.mark.parametrize(
        "name",
        ["xn--nxasmq6b", "XN--NXASMQ6B", "Xn--NxAsMq6B", "www.xn--nxasmq6b.example", "axn--b.example", "a.xn-b"],
    )
    def test_a_label_that_opens_xn_is_an_a_label_of_idna(self, name):
        pytest.importorskip("idna", reason="idna not installed")
        assert_that(_conforms(name, _text_of("hostname"), "3.1.0")).is_true()
        assert_that(_conforms(name, _text_of("hostname"), "3.2.0")).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "xn--X",
            "xn--nxasmq6b0",
            "xn--nxasmq6b.xn--X",
            "a.xn--X.b",
            "xn--" + "a" * 59,
            "xn--l-fda",
            "xn--hello-zed",
        ],
        ids=[
            "no punycode",
            "not the form its own text encodes to",
            "the second of two",
            "between plain labels",
            "too long once decoded",
            "a middle dot with nothing before it",
            "opens with a combining mark",
        ],
    )
    def test_a_label_that_opens_xn_and_is_no_a_label_fails_where_the_dialect_has_a_labels(self, text):
        """JSON Schema took punycode into the format in 2019.  Before it, and so under OpenAPI 3.0 and Swagger
        2.0, a host name is its syntax, which every one of these has."""
        pytest.importorskip("idna", reason="idna not installed")
        assert_that(_conforms(text, _text_of("hostname"), "3.1.0")).is_false()
        assert_that(_conforms(text, _text_of("hostname"), "3.2.0")).is_false()
        assert_that(_conforms(text, _text_of("hostname"), "3.0.3")).is_true()
        assert_that(_conforms(text, _text_of("hostname"), "2.0")).is_true()

    def test_without_the_package_such_a_label_is_refused_with_what_to_install(self):
        with patch.dict(sys.modules, {"idna": None}):
            asked = assert_that(_conforms).raises(ImportError)
            asked.when_called_with("xn--nxasmq6b", _text_of("hostname"), "3.1.0").is_equal_to(
                "idna is required to check an `xn--` label of a hostname. Install it with: pip install assertpy[json]"
            )
            assert_that(_conforms("example.com", _text_of("hostname"), "3.1.0")).is_true()
            assert_that(_conforms("xn--nxasmq6b", _text_of("hostname"), "3.0.3")).is_true()

    def test_the_package_is_loaded_for_such_a_label_and_for_nothing_else(self):
        pytest.importorskip("idna", reason="idna not installed")
        asked = (
            "import sys; from assertpy import json_mixin; loaded = lambda: 'idna' in sys.modules;"
            "before = loaded(); plain = ('example.com', 'not_one', 5, 'axn--b');"
            "took = [json_mixin._is_hostname(one) for one in plain];"
            "between = loaded(); encoded = json_mixin._is_hostname('xn--nxasmq6b');"
            "print(before, took, between, encoded, loaded())"
        )
        ran = subprocess.run([sys.executable, "-c", asked], capture_output=True, text=True, check=True)
        assert_that(ran.stdout.strip()).is_equal_to("False [True, False, True, True] False True True")


class TestATimeIsTheFullTimeOfRfc3339:
    """jsonschema checks `time` by the rule of Draft 3, ``HH:MM:SS`` and no more, whatever is installed."""

    @pytest.mark.parametrize(
        "time",
        [
            "10:00:00Z",
            "10:00:00z",
            "10:00:00+02:00",
            "10:00:00-08:00",
            "10:00:00-00:00",
            "00:00:00Z",
            "23:59:59Z",
            "23:59:59+23:59",
            "23:20:50.52Z",
            "10:00:00.123456789012345Z",
            "23:59:60Z",
            "23:59:60.5Z",
            "01:29:60+01:30",
            "15:59:60-08:00",
            "12:00:60-11:59",
            "23:29:60+23:30",
            "00:29:60-23:30",
        ],
    )
    def test_a_time_passes(self, time):
        assert_that(_conforms(time, _text_of("time"), "3.1.0")).is_true()
        assert_that(_conforms(time, _text_of("time"))).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "10:00:00",
            "10:00:00.5",
            "10:00Z",
            "10Z",
            "1:00:00Z",
            "10:0:00Z",
            "10:00:0Z",
            "010:00:00Z",
            "24:00:00Z",
            "10:60:00Z",
            "10:00:61Z",
            "10:00:00.Z",
            "10:00:00,5Z",
            "10:00:00+2:00",
            "10:00:00+0200",
            "10:00:00+02",
            "10:00:00+24:00",
            "10:00:00+02:60",
            "10:00:00 Z",
            "10:00:00Z ",
            " 10:00:00Z",
            "10:00:00Z\n",
            "10:00:00ZZ",
            "10:00:00+02:00Z",
            "T10:00:00Z",
            "2026-10-06T10:00:00Z",
            "10:00:00UTC",
            "1\u0660:00:00Z",
            "22:59:60Z",
            "23:58:60Z",
            "23:59:60+01:00",
            "00:59:60+01:01",
            "12:00:60-11:58",
        ],
    )
    def test_a_text_that_is_none_fails(self, text):
        assert_that(_conforms(text, _text_of("time"), "3.1.0")).is_false()
        assert_that(_conforms(text, _text_of("time"))).is_false()

    def test_a_time_and_the_time_of_a_moment_are_read_alike(self):
        """One reading for both: what fails as a `time` fails inside a `date-time`, but for the leap second,
        which a `date-time` holds to the last day of a month."""
        for time in ("10:00:00Z", "10:00:00", "24:00:00Z", "10:00:00+24:00", "23:59:60Z"):
            alone = _conforms(time, _text_of("time"))
            assert_that(_conforms(f"2026-12-31T{time}", _text_of("date-time"))).is_equal_to(alone)
        assert_that(_conforms("2026-12-30T23:59:60Z", _text_of("date-time"))).is_false()


class TestADurationIsWrittenAsRfc3339WritesIt:
    """The grammar is appendix A of RFC 3339, which is what the format names, and is narrower than ISO 8601.

    A letter is taken in either case.  RFC 5234 has a quoted letter of an ABNF stand for both, and the official
    suite takes the ``t`` and ``z`` of a `date-time` on that ground."""

    @pytest.mark.parametrize(
        "duration",
        [
            "P1Y",
            "P1M",
            "P1D",
            "P1W",
            "PT1H",
            "PT1M",
            "PT1S",
            "P1Y2M",
            "P1Y2M3D",
            "P2M3D",
            "P3DT4H",
            "P1YT1S",
            "P1MT1M",
            "P1Y2M3DT4H5M6S",
            "PT4H5M",
            "PT5M6S",
            "PT4H5M6S",
            "P0D",
            "PT0S",
            "P001D",
            "P99999999999999999999Y",
            "p1d",
            "pt1h",
            "p1w",
            "p1y2m3dt4h5m6s",
            "P1y2M3dT4h5M6s",
            "pT1S",
        ],
    )
    def test_a_duration_passes(self, duration):
        assert_that(_conforms(duration, _text_of("duration"), "3.1.0")).is_true()
        assert_that(_conforms(duration, _text_of("duration"))).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "P",
            "PT",
            "P1",
            "1D",
            "P1YT",
            "P1DT",
            "PTT1S",
            "PT1D",
            "P1S",
            "P1H",
            "P1D1Y",
            "P1M2M",
            "P1Y1D",
            "PT1H1S",
            "P1DT1H1S",
            "P1DT0.5S",
            "P1W1D",
            "P1D1W",
            "P1WT1H",
            "P1.5D",
            "PT0.5S",
            "PT0,5S",
            "P1e2D",
            "-P1D",
            "+P1D",
            "P-1D",
            "P1D ",
            " P1D",
            "P1D\n",
            "P\u0661D",
            "pt0.5s",
            "pt0,5s",
            "p1w1d",
            "p1y2d",
            "PT1\u017f",
            "\u212a1D",
        ],
    )
    def test_a_text_that_is_none_fails(self, text):
        assert_that(_conforms(text, _text_of("duration"), "3.1.0")).is_false()
        assert_that(_conforms(text, _text_of("duration"))).is_false()

    def test_a_letter_unicode_folds_to_one_of_them_is_none(self):
        """The long ``s`` upper-cases to ``S``, and a pattern told to ignore case takes it for one."""
        assert_that("PT1\u017f".upper()).is_equal_to("PT1S")
        assert_that(re.fullmatch("(?i:PT1S)", "PT1\u017f")).is_not_none()
        assert_that(_conforms("PT1\u017f", _text_of("duration"))).is_false()


class TestAnEmailIsTheMailboxOfRfc5321:
    """jsonschema asks a text for an ``@`` and no more, so ``@`` passed for an address.  The grammar is the
    ``Mailbox`` of RFC 5321, section 4.1.2, which is what the format names.  The 71 cases the official suite
    has for it are held in `tests/test_openapi_format_suite.py`."""

    @pytest.mark.parametrize(
        "address",
        [
            "a@b",
            "a@b.example",
            "A.b-c_d+e@Example.COM",
            "1@2",
            "!#$%&'*+-/=?^_`{|}~@b.example",
            '"a b"@c.example',
            '""@c.example',
            '"a@b"@c.example',
            '"a\\"b"@c.example',
            '"a\\\\"@c.example',
            '"a\\ b"@c.example',
            "a@1.2.3.4",
            "a@" + "x" * 63 + ".example",
            "a@[1.2.3.4]",
            "a@[001.002.003.004]",
            "a@[255.255.255.255]",
            "a@[IPv6:1:2:3:4:5:6:7:8]",
            "a@[IPv6:::]",
            "a@[IPv6:::1]",
            "a@[IPv6:1::]",
            "a@[ipv6:2001:db8::7]",
            "a@[IPV6:2001:DB8::7]",
            "a@[IPv6:1:2:3:4:5:6::]",
            "a@[IPv6:::1:2:3:4:5:6]",
            "a@[IPv6:1:2:3::4:5:6]",
            "a@[IPv6:1:2:3:4:5:6:1.2.3.4]",
            "a@[IPv6:::1.2.3.4]",
            "a@[IPv6:1:2:3:4::1.2.3.4]",
            "a@[IPv6:::1:2:3:4:1.2.3.4]",
            "a@[IPv6:::ffff:1.2.3.04]",
        ],
    )
    def test_an_address_passes(self, address):
        assert_that(_conforms(address, _text_of("email"), "3.1.0")).is_true()
        assert_that(_conforms(address, _text_of("email"))).is_true()

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "a",
            "@",
            "a@",
            "@b",
            "a@b@c",
            "a b@c",
            "a.@b",
            ".a@b",
            "a..b@c",
            "a@b.",
            "a@.b",
            "a@b..c",
            "a@-b",
            "a@b-",
            "a@b_c",
            "a@" + "x" * 64 + ".example",
            "\u00e9@b.example",
            "a@\u00e9.example",
            "a@b.example\n",
            " a@b.example",
            "a@b.example ",
            '"a@b.example',
            '"a"b@c.example',
            '"a"b"@c.example',
            '"a""@c.example',
            '"a"@',
            '"a\u007f"@c.example',
            '"a\\\u00e9"@c.example',
            '"a\\"@c.example',
            "a@[1.2.3]",
            "a@[1.2.3.256]",
            "a@[1.2.3.1000]",
            "a@[1.2.3.4",
            "a@1.2.3.4]",
            "a@[]",
            "a@[::1]",
            "a@[IPv6:]",
            "a@[IPv6:1:2:3:4:5:6:7]",
            "a@[IPv6:1:2:3:4:5:6:7:8:9]",
            "a@[IPv6:1:2:3:4:5:6:7::]",
            "a@[IPv6:::1:2:3:4:5:6:7]",
            "a@[IPv6:1::2:3:4:5:6:7]",
            "a@[IPv6:1:2:3:4:5::1.2.3.4]",
            "a@[IPv6:1:2:3:4::5:1.2.3.4]",
            "a@[IPv6:1:2:3::4:5:6:7]",
            "a@[IPv6:1:2:3:4:5:1.2.3.4]",
            "a@[IPv6:1:2:3:4:5:6:7:1.2.3.4]",
            "a@[IPv6:12345::]",
            "a@[IPv6:g::]",
            "a@[IPv6:1::2::3]",
            "a@[IPv6:::1%eth0]",
            "a@[IPv6:::1.2.3.256]",
            "a@[IPv4:1.2.3.4]",
            "a@[x400:abc]",
            "a@[\u0131Pv6:::1]",
        ],
    )
    def test_a_text_that_is_none_fails(self, text):
        assert_that(_conforms(text, _text_of("email"), "3.1.0")).is_false()
        assert_that(_conforms(text, _text_of("email"))).is_false()

    def test_the_domain_has_the_lengths_of_a_host_name(self):
        """What `format: hostname` holds a name to: 63 characters a label and 253 in all."""
        longest = ".".join(["x" * 63, "x" * 63, "x" * 63, "x" * 61])
        assert_that(len(longest)).is_equal_to(253)
        assert_that(_conforms("a@" + longest, _text_of("email"))).is_true()
        assert_that(_conforms("a@" + longest + "x", _text_of("email"))).is_false()
        assert_that(_conforms("a@" + "x" * 63, _text_of("email"))).is_true()
        assert_that(_conforms("a@" + "x" * 64, _text_of("email"))).is_false()

    def test_the_local_part_has_no_length_in_the_grammar(self):
        """SMTP allows it 64 characters, which is a limit of the transport and none of the ``Mailbox`` rule."""
        for length in (64, 65, 1000, 100_000):
            assert_that(_conforms("a" * length + "@b.example", _text_of("email"))).described_as(length).is_true()
            assert_that(_conforms('"' + "a" * length + '"@b.example', _text_of("email"))).described_as(length).is_true()
            assert_that(_conforms("a" * length + ".@b.example", _text_of("email"))).described_as(length).is_false()
            assert_that(_conforms('"' + "a" * length + '\\"@b.example', _text_of("email"))).described_as(
                length
            ).is_false()

    @pytest.mark.parametrize(
        "local",
        ["a." * 500_000 + "a", '"' + "a" * 1_000_000 + '"', '"' + "\\a" * 500_000 + '"'],
        ids=["atoms and dots", "a quoted string", "quoted pairs"],
    )
    def test_a_megabyte_is_read_without_the_engine_holding_it(self, local):
        """Written as a group that repeats, a megabyte of atoms held 63 MB of the engine's stack and one in quotes
        122: no account of memory shows it, so the pattern is held to having no such group."""
        assert_that(_conforms(local + "@b.example", _text_of("email"))).is_true()
        local_part = json_mixin._MAILBOX[: json_mixin._MAILBOX.index(")@") + 1]
        assert_that(re.findall(r"\)[*+]|\)\{", local_part)).is_empty()


def _abnf_of_rfc_5321() -> Any:
    """Section 4.1.2 of RFC 5321 written out production by production, and the address of 4.1.3 read by counting
    its groups: a second writing of the pattern checked, which spells the address as its alternatives.

    ``General-address-literal`` is left out of both: its tag has to be registered, and ``IPv6`` is the one that
    is.  ``Domain`` has no lengths in the ABNF, and `mailboxes()` holds none past a host name's.
    """
    atext = r"[A-Za-z0-9!#$%&'*+\-/=?^_`{|}~]"
    dot_string = rf"{atext}+(?:\.{atext}+)*"
    qtext_smtp, quoted_pair_smtp = r"[\x20-\x21\x23-\x5b\x5d-\x7e]", r"\x5c[\x20-\x7e]"
    quoted_string = f'"(?:{qtext_smtp}|{quoted_pair_smtp})*"'
    let_dig = "[A-Za-z0-9]"
    sub_domain = f"{let_dig}(?:[A-Za-z0-9-]*{let_dig})?"
    mailbox = re.compile(
        rf"(?:{dot_string}|{quoted_string})@(?:{sub_domain}(?:\.{sub_domain})*|\[(?P<literal>[^\[\]]*)\])"
    )

    def ipv4(text: str) -> bool:
        snums = text.split(".")
        return len(snums) == 4 and all(re.fullmatch("[0-9]{1,3}", snum) and int(snum) <= 255 for snum in snums)

    def ipv6(text: str) -> bool:
        last = text.rsplit(":", 1)[-1]
        ends_in_ipv4 = "." in last
        if ends_in_ipv4:
            if not ipv4(last) or not text[: -len(last)].endswith(":"):
                return False
            text = text[: -len(last)]
            text = text if text.endswith("::") else text[:-1]
        halves = text.split("::")
        hexes = [group for half in halves for group in (half.split(":") if half else [])]
        if len(halves) > 2 or not all(re.fullmatch("[0-9A-Fa-f]{1,4}", group) for group in hexes):
            return False
        if len(halves) == 2:
            return len(hexes) <= (4 if ends_in_ipv4 else 6)
        return len(hexes) == (6 if ends_in_ipv4 else 8)

    def is_mailbox(text: str) -> bool:
        read = mailbox.fullmatch(text)
        if read is None or read.group("literal") is None:
            return read is not None
        literal = read.group("literal")
        return ipv4(literal) or (re.fullmatch("[Ii][Pp][Vv]6:", literal[:5]) is not None and ipv6(literal[5:]))

    return is_mailbox


class TestTheEmailCheckIsTheGrammarWrittenOut:
    def test_over_every_text_of_the_corpus_the_two_writings_agree(self):
        by_the_grammar = _abnf_of_rfc_5321()
        took = 0
        for text in sorted(set(mailboxes())):
            took += by_the_grammar(text)
            assert_that(json_mixin._is_email(text)).described_as(f"{text!r} against the ABNF").is_equal_to(
                by_the_grammar(text)
            )
        assert_that(took).is_greater_than(1000)


class TestEachIsCheckedAlikeEverywhere:
    CASES: typing.ClassVar[dict[str, tuple[str, str]]] = {
        "uri": ("http://example.com/a", "not a uri"),
        "email": ("a@b.example", "a b@c.example"),
        "hostname": ("example.com", "not_a_host"),
        "duration": ("P1D", "a day"),
        "time": ("10:00:00Z", "10:00:00"),
    }

    @pytest.mark.parametrize("form", sorted(CASES))
    @pytest.mark.parametrize("version", ["2.0", "3.0.3", "3.1.0", "3.2.0"])
    def test_in_every_dialect_the_assertion_reads(self, form, version):
        good, bad = self.CASES[form]
        assert_that(_conforms(good, _text_of(form), version)).is_true()
        assert_that(_conforms(bad, _text_of(form), version)).is_false()

    @pytest.mark.parametrize("form", sorted(CASES))
    def test_a_text_of_a_class_of_its_own_is_a_text(self, form):
        good, bad = self.CASES[form]
        named = type("Named", (str,), {})
        assert_that(_conforms(named(good), _text_of(form))).is_true()
        assert_that(_conforms(named(bad), _text_of(form))).is_false()

    @pytest.mark.parametrize("form", sorted(CASES))
    def test_what_is_no_text_is_the_type_keywords_to_judge(self, form):
        assert_that(_conforms(5, {"format": form})).is_true()
        assert_that(_conforms(None, {"format": form})).is_true()
        assert_that(_conforms(5, _text_of(form))).is_false()

    @pytest.mark.parametrize("form", sorted(CASES))
    def test_a_check_jsonschema_brings_of_its_own_does_not_take_its_place(self, form, monkeypatch):
        """Beside the package that gives jsonschema a check of its own, a text still gets the verdict it gets here."""
        asked = []

        def theirs(value: object) -> bool:
            asked.append(value)
            return True

        monkeypatch.setitem(jsonschema.FormatChecker.checkers, form, (theirs, ()))
        good, bad = self.CASES[form]
        assert_that(_conforms(bad, _text_of(form))).is_false()
        assert_that(_conforms(good, _text_of(form))).is_true()
        assert_that(asked).is_empty()

    def test_importing_the_library_compiles_none_of_them_and_loads_no_module_for_them(self):
        """`pathlib` loads `urllib.parse`, and `ipaddress` with it, by itself below Python 3.13."""
        asked = (
            "import re, sys; compiled = []; whole = re.compile;"
            "re.compile = lambda pattern, flags=0: compiled.append(pattern) or whole(pattern, flags);"
            "import assertpy; mixin = assertpy.json_mixin;"
            "ours = (mixin._URI, mixin._HOSTNAME, mixin._DURATION, mixin._MAILBOX);"
            "print([pattern for pattern in compiled if pattern in ours],"
            " sorted({'urllib.parse', 'ipaddress'} & set(sys.modules)) if sys.version_info >= (3, 13) else [])"
        )
        ran = subprocess.run([sys.executable, "-c", asked], capture_output=True, text=True, check=True)
        assert_that(ran.stdout.strip()).is_equal_to("[] []")

    def test_ipaddress_is_loaded_for_an_address_in_brackets_and_for_nothing_else(self):
        asked = (
            "import sys; from assertpy import json_mixin; loaded = lambda: 'ipaddress' in sys.modules;"
            "before = loaded();"
            "took = [json_mixin._is_uri(one) for one in ('http://example.com/a', 'not a uri', 5, 'http://[v1.x]/')];"
            "between = loaded(); address = json_mixin._is_uri('http://[::1]/');"
            "print(before, took, between, address, loaded())"
        )
        ran = subprocess.run([sys.executable, "-c", asked], capture_output=True, text=True, check=True)
        early = sys.version_info < (3, 13)
        assert_that(ran.stdout.strip()).is_equal_to(f"{early} [True, False, True, True] {early} True True")

    def test_the_failure_names_the_place_and_the_format(self):
        outcome = (
            assert_that({"v": "/orders/7"})
            .check()
            .conforms_to_openapi(_spec("3.0.3", _text_of("uri")), "/orders", "get")
        )
        assert_that([(entry.path, entry.actual, entry.expected) for entry in outcome.diff.entries]).is_equal_to(
            [("$.v", "/orders/7", "uri format")]
        )
