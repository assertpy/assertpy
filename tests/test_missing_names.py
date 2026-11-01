"""A key or a name that is not there: the failure says which one that is there reads almost the same.

Asked for ``userid``, a response of forty keys that holds ``user_id`` fails with a sentence that prints the
forty.  Three things are said, the narrowest first, and each only of names: a key reads the same but for its
case, a key reads the same but for how its words are joined, one key alone is spelled almost the same.  The
first two are facts.  The third is a likeness, worded as one, and its rule is measured below on labelled pairs.
"""

from __future__ import annotations

import dataclasses
import difflib

import pytest

from assertpy import AssertionFailure, _hints, assert_that

_PAYLOAD = {"user_id": 2, "Name": "ann", "email": "a@b", "created_at": 1, "items": []}


@dataclasses.dataclass
class _User:
    user_id: int
    first_name: str


def _lines(call) -> list[str]:
    with pytest.raises(AssertionFailure) as caught:
        call()
    return caught.value._message.splitlines()


class TestAKeyThatIsNotThere:
    @pytest.mark.parametrize(
        ("asked", "said"),
        [
            ("name", "a key reads the same but for its case: <Name>"),
            ("EMAIL", "a key reads the same but for its case: <email>"),
            ("userId", "a key reads the same but for how its words are joined: <user_id>"),
            ("userid", "a key reads the same but for how its words are joined: <user_id>"),
            ("created-at", "a key reads the same but for how its words are joined: <created_at>"),
            ("emial", "a key is spelled almost the same: <email>"),
            ("usre_id", "a key is spelled almost the same: <user_id>"),
            ("item", "a key is spelled almost the same: <items>"),
            ("create_at", "a key is spelled almost the same: <created_at>"),
        ],
    )
    def test_the_key_that_reads_almost_the_same_is_named(self, asked, said):
        lines = _lines(lambda: assert_that(_PAYLOAD).contains_key(asked))
        assert_that(lines).is_length(2)
        assert_that(lines[0]).ends_with(f"to contain key <{asked}>, but did not.")
        assert_that(lines[1]).is_equal_to(said)

    @pytest.mark.parametrize("asked", ["address", "id", "user", "zip", "data", "_", ""])
    def test_a_key_like_none_of_them_gets_no_line(self, asked):
        assert_that(_lines(lambda: assert_that(_PAYLOAD).contains_key(asked))).is_length(1)

    def test_every_key_that_reads_the_same_is_named_up_to_three(self):
        held = {"Name": 1, "NAME": 2, "nAME": 3, "naME": 4}
        lines = _lines(lambda: assert_that(held).contains_key("name"))
        assert_that(lines[1]).is_equal_to("a key reads the same but for its case: <Name>, <NAME>, <nAME> and 1 more")
        three = _lines(lambda: assert_that({"Name": 1, "NAME": 2, "nAME": 3}).contains_key("name"))
        assert_that(three[1]).is_equal_to("a key reads the same but for its case: <Name>, <NAME>, <nAME>")
        joined = _lines(lambda: assert_that({"user_id": 1, "userId": 2}).contains_key("user-id"))
        assert_that(joined[1]).is_equal_to("a key reads the same but for how its words are joined: <user_id>, <userId>")

    @pytest.mark.parametrize(
        ("held", "asked"),
        [({"emails": 1, "emai": 2}, "email"), ({"user_ids": 1, "user_idx": 2}, "user_id")],
        ids=["one a letter longer and one a letter shorter", "two a letter longer"],
    )
    def test_two_keys_spelled_almost_the_same_leave_the_choice_unsaid(self, held, asked):
        assert_that(_lines(lambda: assert_that(held).contains_key(asked))).is_length(1)
        for key in held:
            assert_that(_lines(lambda key=key: assert_that({key: 1}).contains_key(asked))[1]).is_equal_to(
                f"a key is spelled almost the same: <{key}>"
            )

    def test_two_keys_of_one_spelling_are_both_named(self):
        lines = _lines(lambda: assert_that({"user_ids": 1, "userIds": 2}).contains_key("user_id"))
        assert_that(lines[1]).is_equal_to("a key is spelled almost the same: <user_ids>, <userIds>")

    def test_a_name_that_is_all_joints_is_like_no_key(self):
        assert_that(_lines(lambda: assert_that({"-": 1, "__": 2}).contains_key("_"))).is_length(1)

    def test_a_fact_is_said_only_of_what_it_says(self):
        # `casefold` calls these two one text, and they differ in more than case
        assert_that(_lines(lambda: assert_that({"Straße": 1}).contains_key("strasse"))).is_length(1)
        assert_that(_lines(lambda: assert_that({"STRASSE": 1}).contains_key("Straße"))).is_length(1)
        # an accent is no joint: the key is a letter longer, which is a likeness and not a fact
        lines = _lines(lambda: assert_that({"cafe\u0301": 1}).contains_key("cafe"))
        assert_that(lines[1]).is_equal_to("a key is spelled almost the same: <cafe\u0301>")
        for joint in ("_", "-", ".", " "):
            joined = _lines(lambda joint=joint: assert_that({f"user{joint}id": 1}).contains_key("userid"))
            assert_that(joined[1]).starts_with("a key reads the same but for how its words are joined: <user")
        assert_that(_lines(lambda: assert_that({"user/id": 1}).contains_key("userid"))[1]).starts_with(
            "a key is spelled almost the same"
        )

    def test_one_key_not_found_among_several_asked_for_is_named(self):
        lines = _lines(lambda: assert_that(_PAYLOAD).contains_key("email", "userid"))
        assert_that(lines[1]).is_equal_to("a key reads the same but for how its words are joined: <user_id>")

    def test_a_long_name_is_not_searched_for_a_likeness(self):
        assert_that(_lines(lambda: assert_that({"k" * 99 + "x": 1}).contains_key("k" * 99))[1]).contains("almost")
        assert_that(_lines(lambda: assert_that({"k" * 100 + "x": 1}).contains_key("k" * 100))).is_length(1)
        assert_that(_lines(lambda: assert_that({"k" * 100: 1}).contains_key("k" * 101))).is_length(1)
        # as they were written, joints and all: taken out, these two are sixty letters against fifty-nine
        assert_that(_lines(lambda: assert_that({"k" * 59: 1}).contains_key("k_" * 60))).is_length(1)
        assert_that(_lines(lambda: assert_that({"k_" * 60: 1}).contains_key("k" * 59))).is_length(1)

    def test_a_fact_is_said_before_a_likeness(self):
        lines = _lines(lambda: assert_that({"emails": 1, "Email": 2}).contains_key("email"))
        assert_that(lines[1]).is_equal_to("a key reads the same but for its case: <Email>")

    def test_several_keys_not_found_get_no_line(self):
        assert_that(_lines(lambda: assert_that(_PAYLOAD).contains_key("name", "userid"))).is_length(1)

    def test_a_key_of_another_type_is_said_first(self):
        lines = _lines(lambda: assert_that({7: "a", "seven": "b"}).contains_key("7"))
        assert_that(lines[1]).is_equal_to(
            "a key reads the same as the key not found and is of another type: int, not str"
        )

    def test_only_keys_that_are_plain_text_are_read(self):
        class Loud(str):
            __slots__ = ()

            def casefold(self) -> str:
                raise RuntimeError("read as a name")

        assert_that(_lines(lambda: assert_that({Loud("Name"): 1, 7: 2, None: 3}).contains_key("name"))).is_length(1)
        assert_that(_lines(lambda: assert_that({"Name": 1}).contains_key(Loud("name")))).is_length(1)
        assert_that(_lines(lambda: assert_that({"Name": 1}).contains_key(b"name"))).is_length(1)

    def test_a_long_key_is_capped_in_the_line(self):
        held = {"K" * 6000: 1}
        lines = _lines(lambda: assert_that(held).contains_key("k" * 6000))
        assert_that(lines[1]).starts_with("a key reads the same but for its case: <KKK").contains("more chars")


class TestEveryAssertionThatLooksAKeyUp:
    """By the name of the assertion, so one that looks a key up and says nothing of it shows here."""

    _SAID = "a key reads the same but for how its words are joined: <user_id>"

    @pytest.mark.parametrize(
        "ask",
        [
            lambda: assert_that(_PAYLOAD).contains_key("userid"),
            lambda: assert_that(_PAYLOAD).contains("userid"),
            lambda: assert_that(_PAYLOAD).contains_entry({"userid": 2}),
            lambda: assert_that(_PAYLOAD).contains_entry(userid=2),
            lambda: assert_that(_PAYLOAD).has_userid(2),
        ],
        ids=["contains_key", "contains on a mapping", "contains_entry", "contains_entry by keyword", "has_<name>"],
    )
    def test_it_names_the_key(self, ask):
        assert_that(_lines(ask)[-1]).is_equal_to(self._SAID)

    def test_a_name_of_an_object_is_called_an_attribute(self):
        lines = _lines(lambda: assert_that(_User(1, "ann")).has_firstname("ann"))
        assert_that(lines).is_equal_to(
            [
                "Expected attribute <firstname>, but val has no attribute <firstname>.",
                "an attribute reads the same but for how its words are joined: <first_name>",
            ]
        )
        assert_that(_lines(lambda: assert_that(_User(1, "ann")).has_zip("x"))).is_length(1)

    def test_the_name_asked_for_is_not_offered_as_one_that_reads_the_same(self):
        class Held:
            @property
            def token(self):
                raise AttributeError("not yet")

        # `hasattr` says the name is not there, and `dir` lists it
        assert_that(_lines(lambda: assert_that(Held()).has_token(1))).is_equal_to(
            ["Expected attribute <token>, but val has no attribute <token>."]
        )

    def test_a_name_that_is_listed_and_not_held_is_not_offered(self):
        class Held:
            def __dir__(self):
                return ["first_name", "user_id"]

            user_id = 1

        assert_that(_lines(lambda: assert_that(Held()).has_firstname(1))).is_length(1)
        assert_that(_lines(lambda: assert_that(Held()).has_userid(1))[1]).ends_with("<user_id>")

    def test_no_code_of_a_listed_name_or_of_a_property_runs_for_the_line(self):
        ran = []

        class Loud(str):
            __slots__ = ()

            def startswith(self, *prefixes) -> bool:
                ran.append("startswith")
                return False

            def __lt__(self, other: object) -> bool:
                ran.append("compared")
                return False

            def __gt__(self, other: object) -> bool:
                ran.append("compared")
                return False

        class Held:
            def __dir__(self):
                return ["user_id", Loud("first_name"), "zip"]

            @property
            def user_id(self):
                ran.append("property")
                return 1

        lines = _lines(lambda: assert_that(Held()).has_userid(1))
        assert_that(lines[1]).is_equal_to("an attribute reads the same but for how its words are joined: <user_id>")
        assert_that(ran).is_empty()

    def test_the_keys_are_walked_once_for_the_line(self):
        class Counted(dict):
            walks = 0

            def __iter__(self):
                Counted.walks += 1
                return super().__iter__()

        assert_that(_lines(lambda: assert_that(Counted(user_id=1)).has_userid(1))).is_length(2)
        assert_that(Counted.walks).is_equal_to(1)

    def test_a_name_asked_under_a_negation_fails_as_it_does_without_one(self):
        # what fails is what the question presupposes, which a negation does not turn round
        lines = _lines(lambda: assert_that({"code": 1}).not_.has_cod(1))
        assert_that(lines).is_equal_to(
            ["Expected key <cod>, but val has no key <cod>.", "a key is spelled almost the same: <code>"]
        )

    def test_a_private_name_is_not_offered(self):
        class Held:
            _token = 1
            token_ = 2

        lines = _lines(lambda: assert_that(Held()).has_token(1))
        assert_that(lines[1]).is_equal_to("an attribute reads the same but for how its words are joined: <token_>")

    def test_an_object_that_cannot_list_its_names_costs_only_the_line(self):
        class Closed:
            def __dir__(self):
                raise RuntimeError("no names")

        assert_that(_lines(lambda: assert_that(Closed()).has_name(1))).is_equal_to(
            ["Expected attribute <name>, but val has no attribute <name>."]
        )

    @pytest.mark.parametrize(
        "ask",
        [
            lambda: assert_that(["admin", "user"]).contains("Admin"),
            lambda: assert_that("Admin").is_in("admin", "user"),
            lambda: assert_that({"role": "admin"}).contains_value("Admin"),
            lambda: assert_that(["admin"]).contains_only("Admin"),
        ],
        ids=["contains on a list", "is_in", "contains_value", "contains_only"],
    )
    def test_a_value_that_is_no_name_gets_no_line_of_a_name(self, ask):
        assert_that("\n".join(_lines(ask))).does_not_contain("spelled", "its case", "joined")

    def test_a_negation_says_nothing_of_it(self):
        assert_that(_lines(lambda: assert_that(_PAYLOAD).does_not_contain_key("email"))).is_length(1)


# a name asked for against the key that was meant
_TYPOS = [
    ("userid", "user_id"), ("user_id", "userid"), ("userId", "user_id"), ("user-id", "user_id"),
    ("usre_id", "user_id"), ("user_di", "user_id"), ("usr_id", "user_id"), ("user_ids", "user_id"),
    ("created", "created_at"), ("createdAt", "created_at"), ("create_at", "created_at"), ("craeted_at", "created_at"),
    ("updated_at", "updatedAt"), ("update_at", "updated_at"), ("first_name", "firstname"), ("fisrt_name", "first_name"),
    ("lastName", "last_name"), ("emial", "email"), ("e_mail", "email"), ("emails", "email"),
    ("adress", "address"), ("addres", "address"), ("phone_number", "phonenumber"), ("phone", "phone_number"),
    ("statuss", "status"), ("staus", "status"), ("descripton", "description"), ("desription", "description"),
    ("item", "items"), ("items", "item"), ("total_count", "totalCount"), ("totalcount", "total_count"),
    ("is_active", "isActive"), ("active", "is_active"), ("order_id", "orderId"), ("ordre_id", "order_id"),
    ("quantity", "quantitiy"), ("qauntity", "quantity"), ("currency", "curency"), ("accessToken", "access_token"),
    ("acces_token", "access_token"), ("refresh_tokn", "refresh_token"), ("page_size", "pageSize"),
    ("pagesize", "page_size"), ("next_page", "nextPage"), ("zip_code", "zipcode"), ("zip", "zip_code"),
    ("country_code", "countryCode"), ("Name", "name"), ("ID", "id"), ("Id", "id"), ("Email", "email"),
    ("TOKEN", "token"), ("Content-Type", "content-type"),
]  # fmt: skip
# two names that are both keys of real payloads and mean two things
_APART = [
    ("date", "data"), ("name", "game"), ("type", "time"), ("status", "state"), ("id", "ip"), ("id", "is"),
    ("user", "uuid"), ("email", "name"), ("email", "address"), ("price", "prize"), ("total", "token"),
    ("items", "times"), ("count", "amount"), ("count", "account"), ("code", "mode"), ("role", "rule"),
    ("title", "tile"), ("order", "owner"), ("start", "state"), ("end", "env"), ("from", "form"),
    ("host", "post"), ("port", "path"), ("size", "site"), ("page", "path"), ("limit", "list"),
    ("value", "values"), ("error", "errors"), ("message", "messages"), ("link", "links"),
    ("created_at", "updated_at"), ("created_at", "deleted_at"), ("first_name", "last_name"),
    ("start_date", "end_date"), ("min_price", "max_price"), ("user_id", "order_id"), ("user_id", "user_name"),
    ("item_1", "item_2"), ("billing_address", "shipping_address"), ("access_token", "refresh_token"), ("x", "y"),
    ("lat", "lng"), ("width", "height"), ("source", "target"), ("request", "response"), ("username", "password"),
]  # fmt: skip


_PAYLOADS = [
    [
        "login",
        "id",
        "node_id",
        "avatar_url",
        "gravatar_id",
        "url",
        "html_url",
        "followers_url",
        "following_url",
        "gists_url",
        "starred_url",
        "subscriptions_url",
        "organizations_url",
        "repos_url",
        "events_url",
        "received_events_url",
        "type",
        "site_admin",
        "name",
        "company",
        "blog",
        "location",
        "email",
        "hireable",
        "bio",
        "twitter_username",
        "public_repos",
        "public_gists",
        "followers",
        "following",
        "created_at",
        "updated_at",
    ],
    [
        "id",
        "object",
        "amount",
        "amount_captured",
        "amount_refunded",
        "application",
        "balance_transaction",
        "billing_details",
        "captured",
        "created",
        "currency",
        "customer",
        "description",
        "disputed",
        "failure_code",
        "failure_message",
        "invoice",
        "livemode",
        "metadata",
        "outcome",
        "paid",
        "payment_intent",
        "payment_method",
        "receipt_email",
        "receipt_number",
        "receipt_url",
        "refunded",
        "refunds",
        "shipping",
        "source",
        "statement_descriptor",
        "status",
        "transfer_data",
        "transfer_group",
    ],
    [
        "orderId",
        "customerId",
        "createdAt",
        "updatedAt",
        "status",
        "totalAmount",
        "currency",
        "items",
        "shippingAddress",
        "billingAddress",
        "paymentMethod",
        "discountCode",
        "taxAmount",
        "notes",
        "trackingNumber",
        "deliveredAt",
        "isGift",
        "giftMessage",
    ],
]


def _slips(name: str) -> set[str]:
    """Every name one step from *name*: a letter dropped, doubled, two swapped, another case, another joining."""
    made = {name.upper(), name.capitalize(), name.replace("_", "")}
    head, *rest = name.split("_")
    made.add(head + "".join(part.capitalize() for part in rest))
    made.add("".join(f"_{letter.lower()}" if letter.isupper() else letter for letter in name))
    for index in range(len(name)):
        made.add(name[:index] + name[index + 1 :])
        made.add(name[:index] + name[index] + name[index:])
        made.add(name[:index] + name[index + 1 : index + 2] + name[index] + name[index + 2 :])
    return made - {name, ""}


class TestTheLineOverWholePayloads:
    """Every key of three payloads, asked for with every slip one step from it, among all the keys of its payload.

    The pairs below are one name against one.  A mapping holds many, with neighbours of its own
    (``followers_url`` beside ``following_url``), and there the line has to name the key meant or keep quiet.
    """

    def test_a_slip_of_a_key_names_that_key_or_nothing_and_never_another(self):
        right = silent = 0
        wrong = []
        for keys in _PAYLOADS:
            for key in keys:
                for name in sorted(_slips(key) - set(keys)):
                    line = _hints._near_name(name, keys, "a key")
                    if line is None:
                        silent += 1
                    elif line.endswith(f": <{key}>"):
                        right += 1
                    else:
                        wrong.append((name, key, line))
        assert_that(wrong).is_empty()
        assert_that((right, silent)).is_equal_to((2511, 18))


class TestTheRuleForSpelledAlmostTheSame:
    """What the rule names and what it leaves, on pairs labelled by hand: the numbers its docstring gives.

    A change of the rule moves these lists, and has to say which way.
    """

    @staticmethod
    def _named(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return [(asked, held) for asked, held in pairs if _hints._near_name(asked, [held], "a key") is not None]

    def test_it_names_all_but_two_of_the_typos(self):
        named = self._named(_TYPOS)
        assert_that(len(_TYPOS)).is_equal_to(54)
        assert_that([pair for pair in _TYPOS if pair not in named]).is_equal_to(
            [("phone", "phone_number"), ("zip", "zip_code")]
        )

    def test_of_two_unrelated_keys_it_names_a_plural_and_two_words_a_slip_apart(self):
        assert_that(len(_APART)).is_equal_to(46)
        assert_that(self._named(_APART)).is_equal_to(
            [
                ("title", "tile"),
                ("from", "form"),
                ("value", "values"),
                ("error", "errors"),
                ("message", "messages"),
                ("link", "links"),
            ]
        )

    @pytest.mark.parametrize(
        ("one", "other", "almost"),
        [
            ("emial", "email", True),
            ("email", "emial", True),
            ("statuss", "status", True),
            ("staus", "status", True),
            ("date", "data", False),
            ("user", "uuid", False),
            ("abcd", "badc", False),
            ("abcde", "ebcda", False),
            ("status", "statussss", False),
            ("createdat", "created", True),
            ("x", "y", False),
            ("a" * 17, "a" * 20, True),
            ("a" * 14, "a" * 20, False),
        ],
    )
    def test_a_slip_is_a_swap_or_a_letter_too_many_or_too_few(self, one, other, almost):
        texts = difflib.SequenceMatcher(None, b=one, autojunk=False)
        assert_that(_hints._almost(one, other, texts)).is_equal_to(almost)
