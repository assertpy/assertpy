import pytest

from tests.optional import needs

needs("attrs")

import attrs
from hypothesis import given, settings
from hypothesis import strategies as st

from assertpy import assert_that
from assertpy.helpers import HelpersMixin


@attrs.define
class Product:
    sku: str
    name: str
    price: float


@attrs.define
class Order:
    id: int
    product: Product
    quantity: int


class TestAttrsIgnore:
    def test_ignore_field(self):
        actual = Product(sku="ABC", name="Widget", price=9.99)
        expected = Product(sku="XYZ", name="Widget", price=9.99)
        assert_that(actual).is_equal_to(expected, ignore="sku")

    def test_include_field(self):
        actual = Product(sku="ABC", name="Widget", price=9.99)
        expected = Product(sku="XYZ", name="Widget", price=0.01)
        assert_that(actual).is_equal_to(expected, include="name")

    def test_nested_attrs_ignore(self):
        actual = Order(id=1, product=Product(sku="A", name="W", price=10.0), quantity=5)
        expected = Order(id=99, product=Product(sku="A", name="W", price=10.0), quantity=5)
        assert_that(actual).is_equal_to(expected, ignore="id")


class TestAttrsListOfObjects:
    def test_list_of_attrs_ignore(self):
        actual = [Product(sku="A", name="W1", price=10.0), Product(sku="B", name="W2", price=20.0)]
        expected = [Product(sku="X", name="W1", price=10.0), Product(sku="Y", name="W2", price=20.0)]
        assert_that(actual).is_equal_to(expected, ignore="sku")


class TestAttrsToComparableDict:
    def test_attrs(self):
        product = Product(sku="A", name="W", price=10.0)
        result = HelpersMixin._to_comparable_dict(product)
        assert_that(result).is_equal_to({"sku": "A", "name": "W", "price": 10.0})


_products = st.builds(Product, sku=st.text(max_size=5), name=st.text(max_size=5), price=st.floats(allow_nan=False))
_orders = st.builds(Order, id=st.integers(), product=_products, quantity=st.integers())


class TestAttrsProperties:
    @settings(deadline=None)
    @given(left=_orders, right=_orders)
    def test_is_equal_to_consistent_with_eq(self, left, right):
        if left == right:
            assert_that(left).is_equal_to(right)
        else:
            with pytest.raises(AssertionError):
                assert_that(left).is_equal_to(right)

    @settings(deadline=None)
    @given(value=_orders)
    def test_is_equal_to_reflexive(self, value):
        assert_that(value).is_equal_to(attrs.evolve(value))

    @settings(deadline=None)
    @given(value=_products, new_sku=st.text(max_size=5))
    def test_ignore_removes_field_difference(self, value, new_sku):
        other = attrs.evolve(value, sku=new_sku)
        assert_that(value).is_equal_to(other, ignore="sku")
