import abc

import pytest

from assertpy import assert_that


class Person:
    def __init__(self, first_name, last_name):
        self.first_name = first_name
        self.last_name = last_name

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}"

    def say_hello(self):
        return f"Hello, {self.first_name}!"

    def __str__(self) -> str:
        return self.name


class Developer(Person):
    def say_hello(self):
        return f"{self.first_name} writes code."


class AbstractAutomobile(abc.ABC):
    @property
    @abc.abstractmethod
    def classification(self):
        raise NotImplementedError("This method must be overridden")


class Car(AbstractAutomobile):
    @property
    def classification(self):
        return "car"


class Truck(AbstractAutomobile):
    @property
    def classification(self):
        return "truck"


fred = Person("Fred", "Smith")
joe = Developer("Joe", "Coder")
people = [fred, joe]
car = Car()
truck = Truck()


def test_is_type_of():
    assert_that(fred).is_type_of(Person)
    assert_that(joe).is_type_of(Developer)
    assert_that(car).is_type_of(Car)
    assert_that(truck).is_type_of(Truck)


def test_is_type_of_class():
    assert_that(fred.__class__).is_type_of(Person.__class__)


def test_is_type_of_class_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred.__class__).is_type_of(Person)
    assert_that(str(exc_info.value)).contains("to be of type <Person>, but was not")


def test_is_instance_of():
    assert_that(fred).is_instance_of(Person)
    assert_that(fred).is_instance_of(object)

    assert_that(joe).is_instance_of(Developer)
    assert_that(joe).is_instance_of(Person)
    assert_that(joe).is_instance_of(Person | Developer)
    assert_that(joe).is_instance_of((Person, Developer))
    assert_that(joe).is_instance_of(object)

    assert_that(car).is_instance_of(Car)
    assert_that(car).is_instance_of(AbstractAutomobile)
    assert_that(car).is_instance_of(object)

    assert_that(truck).is_instance_of(Truck)
    assert_that(truck).is_instance_of(AbstractAutomobile)
    assert_that(truck).is_instance_of(object)


def test_is_instance_of_class():
    assert_that(fred.__class__).is_instance_of(Person.__class__)
    assert_that(fred.__class__).is_instance_of(Car.__class__ | Person.__class__)
    assert_that(fred.__class__).is_instance_of((Car.__class__, Person.__class__))


def test_is_instance_of_class_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred.__class__).is_instance_of(Person)
    assert_that(str(exc_info.value)).contains("to be instance of class <Person>, but was not")

    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).is_instance_of(Car | str)
    assert_that(str(exc_info.value)).contains("to be instance of class <Car | str>, but was not")

    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).is_instance_of((Car, str))
    assert_that(str(exc_info.value)).contains("to be instance of class <Car, str>, but was not")


def test_is_instance_of_any():
    assert_that(fred).is_instance_of_any(Person)
    assert_that(fred).is_instance_of_any(Car | Person)
    assert_that(fred).is_instance_of_any(Truck, Car | Person)


def test_is_instance_of_any_failure():
    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).is_instance_of_any(Truck, Car)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <Fred Smith:Person> to be instance of any of <Truck, Car>, but was not."
    )

    with pytest.raises(AssertionError) as exc_info:
        assert_that(fred).is_instance_of_any(Developer, Car | Truck)
    assert_that(str(exc_info.value)).is_equal_to(
        "Expected <Fred Smith:Person> to be instance of any of <Developer, Car | Truck>, but was not."
    )


def test_extract_attribute():
    assert_that(people).extracting("first_name").is_equal_to(["Fred", "Joe"])
    assert_that(people).extracting("first_name").contains("Fred", "Joe")


def test_extract_property():
    assert_that(people).extracting("name").contains("Fred Smith", "Joe Coder")


def test_extract_multiple():
    assert_that(people).extracting("first_name", "name").contains(("Fred", "Fred Smith"), ("Joe", "Joe Coder"))


def test_extract_zero_arg_method():
    assert_that(people).extracting("say_hello").contains("Hello, Fred!", "Joe writes code.")
