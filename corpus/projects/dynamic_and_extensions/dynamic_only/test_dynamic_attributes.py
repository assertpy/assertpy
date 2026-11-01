"""`has_<attribute>()` on a plain class: it runs, and no checker is told about it.

The typed surface stopped offering it when a value with no capability stopped reaching the full
builder, which is where `__getattr__` lives.  Runtime behaviour did not change, and the documented
migration is to assert on the attribute rather than through it:
`assert_that(account.owner).is_equal_to("alice")`.  Both spellings are exercised here, so the day the
runtime stops answering the first one, this project says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from assertpy import assert_that


@dataclass
class Account:
    owner: str
    balance: float

    def is_overdrawn(self) -> bool:
        return self.balance < 0


def test_dynamic_attribute_assertions_read_the_object() -> None:
    account = Account("alice", 120.0)
    assert_that(account).has_owner("alice")
    assert_that(account).has_balance(120.0)


def test_dynamic_assertions_reach_a_zero_argument_method() -> None:
    assert_that(Account("bob", -5.0)).has_is_overdrawn(True)


def test_the_migration_the_documentation_gives() -> None:
    account = Account("alice", 120.0)
    assert_that(account.owner).is_equal_to("alice")
    assert_that(account.balance).is_equal_to(120.0)
    assert_that(account.is_overdrawn()).is_false()
