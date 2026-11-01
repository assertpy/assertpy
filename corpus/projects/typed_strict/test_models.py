"""Everything annotated, checked at maximum strictness, over the model shapes a service test uses.

The opposite end from `pytest_style`.  A typed surface that fits loose code and not this is a surface a
typed codebase cannot adopt, and that is the audience this library sells its overloads to.
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Sequence  # noqa: TC003  # consumer code, written plainly on purpose

import attrs
import pydantic

from assertpy import assert_that, match, soft_assertions


@dataclasses.dataclass
class Order:
    identifier: int
    customer: str
    total: float
    items: list[str]


@attrs.define
class Shipment:
    identifier: int
    carrier: str
    delivered: bool


class Customer(pydantic.BaseModel):
    name: str
    age: int
    tags: list[str] = pydantic.Field(default_factory=list)


def orders() -> list[Order]:
    return [
        Order(identifier=1, customer="alice", total=120.5, items=["book", "pen"]),
        Order(identifier=2, customer="bob", total=12.0, items=["pen"]),
    ]


def test_a_dataclass_keeps_its_field_types_through_the_chain() -> None:
    order: Order = orders()[0]
    assert_that(order.total).is_greater_than(100.0)
    assert_that(order.items).contains("book").is_length(2)
    assert_that(order.customer).starts_with("ali")


def test_the_pipeline_keeps_the_element_type() -> None:
    expensive: Sequence[Order] = [order for order in orders() if order.total > 100]
    assert_that(list(expensive)).is_length(1)

    totals: list[float] = assert_that(orders()).mapped(lambda order: order.total).value
    assert_that(totals).is_equal_to([120.5, 12.0])

    names: list[str] = (
        assert_that(orders()).filtered_on(lambda order: order.total > 50).mapped(lambda order: order.customer).value
    )
    assert_that(names).is_equal_to(["alice"])


def test_structural_comparison_reads_a_model() -> None:
    customer = Customer(name="alice", age=30, tags=["vip"])
    assert_that(customer).has_name("alice")
    assert_that(customer).matches_structure({"name": match.is_type_of(str), "age": match.is_type_of(int)})
    assert_that(customer.tags).contains("vip")


def test_attrs_values_compare_field_by_field() -> None:
    shipment = Shipment(identifier=1, carrier="dhl", delivered=False)
    assert_that(shipment.carrier).is_equal_to("dhl")
    assert_that(shipment.delivered).is_false()


def test_matchers_carry_the_type_they_judge() -> None:
    assert_that(orders()[0].items).satisfies(match.contains("pen"))
    assert_that(orders()[0].total).satisfies(match.greater_than(100.0))
    assert_that(orders()).each(lambda order: order.total > 0)


def test_a_soft_block_keeps_the_annotations_of_its_body() -> None:
    collected: list[str] = []
    try:
        with soft_assertions():
            for order in orders():
                collected.append(order.customer)
                assert_that(order.total).is_greater_than(100.0)
    except AssertionError as failure:
        assert_that(str(failure)).contains("12.0")
    assert_that(collected).is_equal_to(["alice", "bob"])


def test_the_value_of_an_extraction_is_a_list() -> None:
    extracted: list[object] = assert_that(orders()).extracting("customer").value
    assert_that(extracted).is_equal_to(["alice", "bob"])


def test_subset_leaves_the_chain_on_the_same_view() -> None:
    """The argument is untyped by measurement, but what comes back still knows its element."""
    names: list[str] = [order.customer for order in orders()]
    assert_that(names).is_subset_of(["alice", "bob", "carol"]).contains("alice")
    kept: list[str] = assert_that(names).is_subset_of(["alice", "bob", "carol"]).filtered_on(lambda name: True).value
    assert_that(kept).is_equal_to(names)
    assert_that(orders()[0].items).is_subset_of({"book", "pen"}).is_length(2)


if sys.version_info >= (3, 11):

    def failing_tasks() -> None:
        raise ExceptionGroup(  # noqa: F821  # ruff reads the repo floor of 3.10, where it is not a builtin
            "2 tasks failed", [ValueError("bad id"), KeyError("missing")]
        )

    def test_a_group_answers_through_the_typed_surface() -> None:
        caught = assert_that(failing_tasks).raises(ExceptionGroup).when_called_with()  # noqa: F821  # as above
        caught.contains_error(ValueError, KeyError).does_not_contain_error(TimeoutError)
        leaves: list[BaseException] = caught.errors().value
        assert_that(leaves).is_length(2)
        message: str = caught.error_of(ValueError).value
        assert_that(message).contains("bad id")
        caught.error_of(ValueError).raised().is_instance_of(ValueError)
