"""HTML read into a tree, for `is_html_equal_to()` and `match.html_equal_to()`: one reader, one comparison.

The markup is tokenized by the standard library's `html.parser`, and the tree is built here, as Django's
``assertHTMLEqual`` builds it: an end tag closes the elements opened after its own, an element left open at
the end is closed, and there is no other tree construction, so ``<p>a<p>b`` nests.  A slash on a non-void
element is ignored, as the standard reads it.  SVG and MathML are refused: their own rules for slashes,
CDATA, text and attributes, and where they hand content back to HTML, took more than a reader of this size
gets right.  The parser's text modes
are fixed here rather than taken from the running Python: patch releases from 2025 on read ``textarea``,
``title``, ``xmp``, ``iframe``, ``noembed``, ``noframes`` and ``plaintext`` as text, older ones read markup
inside them, and the same comparison must not pass on one and fail on the other.
"""

from __future__ import annotations

import html
import re
import string
from html.entities import html5
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

from ._engine._require import argument, raised_on_purpose, refuse

if TYPE_CHECKING:
    from collections.abc import Iterator

__tracebackhide__ = raised_on_purpose

Whitespace: TypeAlias = Literal["lenient", "exact"]
Attributes: TypeAlias = tuple[tuple[str, str | None], ...]
Node: TypeAlias = "str | tuple[str, Attributes, tuple[Node, ...]]"
"""Text, or an element: its name, its attributes sorted by name (``None`` for one read by presence), its children."""

_WHITESPACE_RUN: Final = re.compile(r"[\t\n\f\r ]+")
_ASCII_WHITESPACE: Final = "\t\n\f\r "
_UNREAD_MARKUP: Final = re.compile(r"<(?:[A-Za-z!?]|/.)", re.DOTALL)
_END_TAG: Final = re.compile(r"</([A-Za-z][^\t\n\r\f />]*)")
_NAME: Final = re.compile(r"[a-zA-Z][^\t\n\r\f />]*")
_SPACED_CLOSE: Final = re.compile(r"--\s+>")
_ASCII_LOWER: Final = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)
_RAW_END: Final = re.compile(r"</[A-Za-z]+[\t\n\f ]*>")
# the tag name and attribute patterns of html.parser from its 2025 fixes on, which follow the standard's tokenizer
_TAG_NAME: Final = re.compile(r"[a-zA-Z][^\t\n\r\f />]*(?:[\t\n\r\f ]|/(?!>))*")
_ATTRIBUTE: Final = re.compile(
    r"""((?<=['"\t\n\r\f /])[^\t\n\r\f />][^\t\n\r\f /=>]*)"""
    r"""([\t\n\r\f ]*=[\t\n\r\f ]*('[^']*'|"[^"]*"|(?!['"])[^>\t\n\r\f ]*))?(?:[\t\n\r\f ]|/(?!>))*"""
)
_REFERENCE: Final = re.compile(r"&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*)[;=]?")
# a space `\s` finds and the standard does not: a parser before 2025 split an unquoted value at it
_OTHER_SPACE: Final = re.compile(r"[^\S\t\n\f\r ]")
_UNQUOTED_ERROR: Final = re.compile(r"[\"'<=`]")
_NUMERIC_REFERENCE: Final = re.compile(r"&#(?:[xX][0-9a-fA-F]+|[0-9]+);?")

# the void elements of the standard's syntax section, and the obsolete ones its tree construction also closes at once
_VOID: Final = frozenset(
    {
        *("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"),
        *("basefont", "bgsound", "frame", "keygen", "param"),
    }
)
_RAW_TEXT: Final = ("script", "style", "xmp", "iframe", "noembed", "noframes", "plaintext")
_ESCAPABLE_RAW_TEXT: Final = ("textarea", "title")
_NEWLINE_DROPPED: Final = frozenset({"pre", "listing"})
_VERBATIM: Final = frozenset({"pre", "listing", "textarea", *_RAW_TEXT})
_FOREIGN: Final = frozenset({"svg", "math"})
# 256 deep is read, compared and rendered 200 frames down a stack on 3.10 and 3.15; far deeper meets the recursion limit
_DEEPEST: Final = 256

# the boolean attributes of the standard's attribute index, by the elements they are boolean on; None is every one
_BOOLEAN: Final[dict[str, frozenset[str] | None]] = {
    "allowfullscreen": frozenset({"iframe"}),
    "alpha": frozenset({"input"}),
    "async": frozenset({"script"}),
    "autofocus": None,
    "autoplay": frozenset({"audio", "video"}),
    "checked": frozenset({"input"}),
    "controls": frozenset({"audio", "video", "img"}),
    "default": frozenset({"track"}),
    "defer": frozenset({"script"}),
    "disabled": frozenset({"button", "fieldset", "input", "link", "optgroup", "option", "select", "textarea"}),
    "formnovalidate": frozenset({"button", "input"}),
    "headingreset": None,
    "inert": None,
    "ismap": frozenset({"img"}),
    "itemscope": None,
    "loop": frozenset({"audio", "video"}),
    "multiple": frozenset({"input", "select"}),
    "muted": frozenset({"audio", "video"}),
    "nomodule": frozenset({"script"}),
    "novalidate": frozenset({"form"}),
    "open": frozenset({"details", "dialog"}),
    "playsinline": frozenset({"video"}),
    "readonly": frozenset({"input", "textarea"}),
    "required": frozenset({"input", "select", "textarea"}),
    "reversed": frozenset({"ol"}),
    "selected": frozenset({"option"}),
    "shadowrootclonable": frozenset({"template"}),
    "shadowrootcustomelementregistry": frozenset({"template"}),
    "shadowrootdelegatesfocus": frozenset({"template"}),
    "shadowrootserializable": frozenset({"template"}),
}


class _Open:
    """An element being read: what the tree will hold, and how its text is to be read."""

    __slots__ = ("attributes", "children", "fresh", "name", "verbatim")

    def __init__(self, name: str, attributes: Attributes, *, verbatim: bool) -> None:
        self.name = name
        self.attributes = attributes
        self.children: list[str | _Open] = []
        self.verbatim = verbatim
        self.fresh = True


class _Reader(HTMLParser):
    """Builds the tree from the tokens, and keeps the first reason the markup cannot be read instead of raising it.

    Raising from a handler would put frames of `html.parser` in the traceback of a refusal, so `read_html`
    raises the reason once the parser has returned.
    """

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.text = text
        self.lines = [0, *(found.end() for found in re.finditer("\n", text))]
        self.root = _Open("", (), verbatim=False)
        self.open: list[_Open] = [self.root]
        self.problem: str | None = None

    def set_cdata_mode(self, elem: str, **_: object) -> None:
        # one rule on every version: a newer one asks with `escapable=` and ends the text at another tag
        self.cdata_elem = elem.lower()
        self._escapable = False
        ending = r"\Z" if self.cdata_elem == "plaintext" else rf"</{self.cdata_elem}(?=[\t\n\r\f />])"
        self.interesting = re.compile(ending, re.IGNORECASE | re.ASCII)

    def _written(self) -> str:
        """The text from the token being handled on: what the parser read it from."""
        line, column = self.getpos()
        return self.text[self.lines[line - 1] + column :]

    def refuse(self, reason: str) -> None:
        if self.problem is None:
            line, column = self.getpos()
            self.problem = f"{reason}, at line {line}, column {column + 1}"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = self._opened(tag, attrs)
        if element is not None and (element.name in _RAW_TEXT or element.name in _ESCAPABLE_RAW_TEXT):
            self.set_cdata_mode(element.name)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = self._opened(tag, attrs)
        if element is None or element.name in _VOID:
            return
        if element.name in _RAW_TEXT or element.name in _ESCAPABLE_RAW_TEXT:
            self.refuse(f"<{element.name}/> does not close in HTML, so the rest of the text would be its content")
        # any other HTML element: the slash is ignored, and the element stays open

    def _opened(self, tag: str, attrs: list[tuple[str, str | None]]) -> _Open | None:
        if self.problem is not None:
            return None
        parent = self.open[-1]
        parent.fresh = False
        written = self.get_starttag_text()
        if written is not None:
            named = _NAME.match(written, 1)
            read = _attributes_written(written)
            if (
                named is None
                or read is None
                or named.group().lower() != tag
                or [name.lower() for name, _ in read] != [name for name, _ in attrs]
            ):
                self.refuse(f"<{tag}> is not read alike on every Python version")
                return None
            tag = _ascii_lower(named.group())
            attrs = read
        if tag in _FOREIGN:
            self.refuse(f"<{tag}> holds {'SVG' if tag == 'svg' else 'MathML'}, which this comparison does not read")
            return None
        if len(self.open) > _DEEPEST:
            self.refuse(f"elements are nested deeper than {_DEEPEST}")
            return None
        seen: set[str] = set()
        for name, _ in attrs:
            if name in seen:
                self.refuse(f"<{tag}> has the attribute {name!r} twice")
                return None
            seen.add(name)
        element = _Open(tag, _attributes(tag, attrs), verbatim=parent.verbatim or tag in _VERBATIM)
        parent.children.append(element)
        if tag not in _VOID:
            self.open.append(element)
        return element

    def handle_endtag(self, tag: str) -> None:
        written = self._written()
        named = _END_TAG.match(written)
        if named is None or named.group(1).lower() != tag:
            self.refuse("</ is not followed by the name of an element")
            return
        tag = _ascii_lower(named.group(1))
        if (tag in _RAW_TEXT or tag in _ESCAPABLE_RAW_TEXT) and self.cdata_elem and not _RAW_END.match(written):
            self.refuse(f"the end tag of <{tag}> holds more than its name")
        self._closed(tag)

    def _closed(self, tag: str) -> None:
        if self.problem is not None:
            return
        for depth in range(len(self.open) - 1, 0, -1):
            if self.open[depth].name == tag:
                del self.open[depth:]
                self.open[-1].fresh = False
                return
        self.refuse(f"</{tag}> closes no open <{tag}>")

    def handle_data(self, data: str) -> None:
        if self.cdata_elem not in (None, "plaintext") and re.search(
            rf"</{self.cdata_elem}[\t\n\f />]", data, re.IGNORECASE | re.ASCII
        ):
            self.refuse(f"the end tag of <{self.cdata_elem}> holds more than its name")
        self._text(data)

    def _text(self, data: str) -> None:
        parent = self.open[-1]
        if parent.fresh and parent.name in _NEWLINE_DROPPED and data[:1] == "\n":
            data = data[1:]
        parent.fresh = False
        if not data:
            return
        if parent.children and isinstance(parent.children[-1], str):
            parent.children[-1] += data
        else:
            parent.children.append(data)

    def handle_comment(self, data: str) -> None:
        """A comment is not compared, but it is a token, and four ways of writing one are read differently by
        the parser before and after its 2025 fixes, so they are refused rather than read one way or the other."""
        self.open[-1].fresh = False
        written = self._written()
        if written.startswith("</"):
            self.refuse("</ is not followed by the name of an element")
        elif written.startswith("<!["):
            self.refuse("a marked section, which HTML ends at its first > and Python's parser does not")
        elif written.startswith(("<!-->", "<!--->")):
            self.refuse("a comment is closed by the > right after its <!--")
        elif written.startswith("<!--") and ("--!>" in data or written.startswith("--!>", 4 + len(data))):
            self.refuse("a comment is closed by --!>")
        elif written.startswith("<!--") and (_SPACED_CLOSE.search(data) or _SPACED_CLOSE.match(written, 4 + len(data))):
            self.refuse("a comment holds -- and spaces before a >, where an older parser closes it")

    def handle_decl(self, decl: str) -> None:
        del decl
        self.open[-1].fresh = False

    def handle_pi(self, data: str) -> None:
        del data
        self.open[-1].fresh = False

    def unknown_decl(self, data: str) -> None:
        del data
        self.open[-1].fresh = False
        self.refuse("a marked section, which HTML ends at its first > and Python's parser does not")


def _ascii_lower(name: str) -> str:
    """*name* with ASCII upper case lowered and nothing else: HTML folds names so, and ``K`` (U+212A) stays."""
    return name.translate(_ASCII_LOWER)


def _attributes_written(start_tag: str) -> list[tuple[str, str | None]] | None:
    """The attributes of *start_tag*, its text as written, each value decoded as the standard decodes a value.

    A named reference without its ``;`` is decoded only where the name is one the standard allows so and no
    ``=`` follows: ``?a=1&not=2`` stays as it is, where every reference in text is decoded.  ``None`` where a
    name or an unquoted value holds a space that is not ASCII, at which a parser before 2025 split it, or an
    unquoted value holds a character the standard calls a parse error there, which it read otherwise too.
    """
    name = _TAG_NAME.match(start_tag, 1)
    at = name.end() if name else len(start_tag)
    found: list[tuple[str, str | None]] = []
    while (attribute := _ATTRIBUTE.match(start_tag, at)) is not None:
        key, given, value = attribute.group(1, 2, 3)
        if not given:
            value = None
        elif value[:1] == value[-1:] and value[:1] in ("'", '"'):
            value = value[1:-1]
        elif _OTHER_SPACE.search(value) or _UNQUOTED_ERROR.search(value):
            return None
        if _OTHER_SPACE.search(key):
            return None
        found.append((_ascii_lower(key), _REFERENCE.sub(_decoded, value) if value else value))
        at = attribute.end()
    return found


def _decoded(reference: re.Match[str]) -> str:
    written = reference.group(0)
    if written.startswith("&#") or (not written.endswith("=") and written[1:] in html5):
        return html.unescape(written)
    return written


def _attributes(tag: str, attrs: list[tuple[str, str | None]]) -> Attributes:
    """The attributes of a start tag as they compare: a boolean one by presence, ``hidden`` by its state, ``class``
    as its tokens in order, the rest as written."""
    kept: list[tuple[str, str | None]] = []
    for name, value in attrs:
        on = _BOOLEAN.get(name, frozenset())
        if on is None or tag in on:
            kept.append((name, None))
        elif name == "hidden":
            kept.append((name, "until-found" if (value or "").lower() == "until-found" else None))
        elif name == "class":
            kept.append((name, " ".join(sorted(token for token in _WHITESPACE_RUN.split(value or "") if token))))
        else:
            kept.append((name, value or ""))
    return tuple(sorted(kept, key=lambda pair: pair[0]))


def whitespace_mode(whitespace: object) -> Whitespace:
    """*whitespace* as one of the modes, refused unless it is one."""
    if not isinstance(whitespace, str):
        refuse(whitespace, "'lenient' or 'exact'", subject=argument("whitespace"))
    if whitespace == "lenient" or whitespace == "exact":
        return whitespace
    _assertpy_refusal = True
    raise ValueError(f"given whitespace arg must be 'lenient' or 'exact', but was {whitespace!r}")


def read_html(text: str, whitespace: Whitespace, *, subject: str) -> tuple[Node, ...]:
    """*text* as the nodes at its top, its text read by the *whitespace* rules.

    Raises:
        ValueError: where the markup cannot be read: an end tag that closes no open element, a repeated
            attribute, a ``script``, ``textarea`` or another element holding raw text left open, text that ends
            inside a tag, a comment or a declaration, a raw-text element written with a slash, a marked
            section, a NUL, a numeric reference Python's decoder drops, ``svg`` or
            ``math``, elements nested more than 256 deep, or a spelling the parser reads differently before
            and after its 2025
            fixes: a comment closed as ``<!-->``, by ``--!>`` or by ``--`` and spaces, ``</`` and no letter, a
            raw-text end tag with more than its name, a non-ASCII space in an attribute's name or a value
            without quotes, or such a value holding a quote, ``=``, ``<`` or a backtick.
            *subject* names the side in the message.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    reader = _Reader(text)
    dropped = next((found for found in _NUMERIC_REFERENCE.finditer(text) if not html.unescape(found.group())), None)
    if "\x00" in text:
        line = text.count("\n", 0, text.index("\x00")) + 1
        reader.problem = f"it holds a NUL character, which Python versions read differently, at line {line}"
    elif dropped is not None:
        line = text.count("\n", 0, dropped.start()) + 1
        reader.problem = (
            f"{dropped.group()} names a control character or a noncharacter, which Python's decoder drops,"
            f" at line {line}"
        )
    else:
        try:
            reader.feed(text)
        except AssertionError:
            # a parser before 2025 asserts on a marked section it does not know, as `<![foo]>`
            reader.refuse("a marked section, which HTML ends at its first > and Python's parser does not")
    if reader.cdata_elem not in (None, "plaintext"):
        reader.refuse(f"<{reader.cdata_elem}> is not closed, so the rest of the text would be its content")
    if _UNREAD_MARKUP.match(reader.rawdata):
        unread = reader.rawdata if len(reader.rawdata) <= 30 else reader.rawdata[:30] + "..."
        reader.refuse(f"the text ends inside {unread!r}")
    if reader.problem is not None:
        _assertpy_refusal = True
        raise ValueError(f"{subject} is not HTML that can be read: {reader.problem}")
    reader.close()
    return _children(reader.root, whitespace)


def _children(element: _Open, whitespace: Whitespace) -> tuple[Node, ...]:
    """The children of *element* as the tree holds them, text read by the *whitespace* rules where not verbatim."""
    children: list[Node] = []
    for child in element.children:
        if isinstance(child, _Open):
            children.append((child.name, child.attributes, _children(child, whitespace)))
            continue
        if element.name in _ESCAPABLE_RAW_TEXT:
            child = html.unescape(child)
            if element.name == "textarea" and child[:1] == "\n":
                child = child[1:]
        if not element.verbatim and whitespace == "lenient":
            child = _WHITESPACE_RUN.sub(" ", child).strip(_ASCII_WHITESPACE)
        if child:
            children.append(child)
    return tuple(children)


def rendered(nodes: tuple[Node, ...]) -> str:
    """*nodes* written one to a line, indented by depth, attributes sorted and every text quoted.

    Two trees render alike only where they are equal, so the rendering is what a failure shows and diffs.
    """
    return "\n".join(_lines(nodes, 0))


def _lines(nodes: tuple[Node, ...], depth: int) -> Iterator[str]:
    indent = "  " * depth
    for node in nodes:
        if isinstance(node, str):
            yield indent + _quoted(node)
            continue
        name, attributes, children = node
        written = (key if value is None else f"{key}={_quoted(value)}" for key, value in attributes)
        opening = "<" + " ".join([name, *written]) + ">"
        if name in _VOID:
            yield indent + opening
        elif not children:
            yield f"{indent}{opening}</{name}>"
        elif len(children) == 1 and isinstance(children[0], str):
            yield f"{indent}{opening}{_quoted(children[0])}</{name}>"
        else:
            yield indent + opening
            yield from _lines(children, depth + 1)
            yield f"{indent}</{name}>"


_ESCAPES: Final = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\t": "\\t", "\r": "\\r", "\f": "\\f"}


def _escape(char: str) -> str:
    """*char* as a Python string literal spells it: four hex digits up to U+FFFF, eight above, so none reads as two."""
    code = ord(char)
    return f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}"


def _quoted(text: str) -> str:
    """*text* in double quotes, every whitespace but the space and every unprintable character escaped."""
    escaped = (_ESCAPES.get(char) or (char if char.isprintable() else _escape(char)) for char in text)
    return '"' + "".join(escaped) + '"'
