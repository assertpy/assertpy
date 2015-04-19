# assertpy

Dead simple assertions framework for unit testing in Python with a nice fluent API.

[![Build Status](https://travis-ci.org/ActivisionGameScience/assertpy.svg?branch=master)](https://travis-ci.org/ActivisionGameScience/assertpy)
[![Coverage Status](https://coveralls.io/repos/ActivisionGameScience/assertpy/badge.png)](https://coveralls.io/r/ActivisionGameScience/assertpy)

## Usage

Just import the `assert_that` function, and away you go...

```py
from assertpy import assert_that

class TestSomething(object):

    def test_something(self):
        assert_that(1 + 2).is_equal_to(3)
        assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')
```

Of course, `assertpy` works best with a python test runner like [Nose](http://nose.readthedocs.org/) or [pytest](http://pytest.org/latest/contents.html).

## Installation

The `assertpy` framework is available via [PyPI](https://pypi.python.org/pypi/assertpy).
Just install with:

```
pip install assertpy
```

Or, if you are a big fan of [conda](http://conda.pydata.org/) like we are, `assertpy` is also on [binstar](https://binstar.org/ActivisionGameScience/assertpy).
Just install from our channel:

```
conda install --channel ActivisionGameScience assertpy
```

## The API

The fluent API of `assertpy` is designed to create compact, yet readable tests.
The API has been modeled after other fluent testing APIs, especially the awesome 
[AssertJ](http://joel-costigliola.github.io/assertj/) assertion framework for Java.  Of course, in the `assertpy` framework everything is fully pythonic and designed to take full advantage of the dynamism in the Python runtime.

### Strings

Matching strings:

```py
assert_that('').is_not_none()
assert_that('').is_empty()
assert_that('').is_false()
assert_that('').is_type_of(str)
assert_that('').is_instance_of(str)

assert_that('foo').is_length(3)
assert_that('foo').is_not_empty()
assert_that('foo').is_true()
assert_that('foo').is_alpha()
assert_that('123').is_digit()
assert_that('foo').is_lower()
assert_that('FOO').is_upper()
assert_that('foo').is_equal_to('foo')
assert_that('foo').is_not_equal_to('bar')
assert_that('foo').is_equal_to_ignoring_case('FOO')

assert_that('foo').contains('f')
assert_that('foo').contains('f','oo')
assert_that('foo').does_not_contain('x')
assert_that('foo').contains_sequence('o','o')

assert_that('foo').contains_duplicates()
assert_that('fox').does_not_contain_duplicates()

assert_that('foo').is_in('foo','bar','baz')
assert_that('foo').is_not_in('boo','bar','baz')

assert_that('foo').starts_with('f')
assert_that('foo').ends_with('oo')

assert_that('foo').matches(r'\w')
assert_that('123-456-7890').matches(r'\d{3}-\d{3}-\d{4}')
assert_that('foo').does_not_match(r'\d+')
```

Regular expressions can be tricky.  Be sure to use raw strings (prefix the pattern string with `r`) for the regex pattern to be match.  Also, note that the `matches()` function passes for partial matches (as does the [re.match](https://docs.python.org/2/library/re.html#re.match) function that underlies it). If you want to match the entire string, just include anchors in the regex pattern.

```py
# partial matches, these all pass
assert_that('foo').matches(r'\w') 
assert_that('foo').matches(r'oo')
assert_that('foo').matches(r'\w{2}')

# match the entire string with an anchored regex pattern, passes
assert_that('foo').matches(r'^\w{3}$')

# fails
assert_that('foo').matches(r'^\w{2}$')
```

### Numbers

Matching integers:

```py
assert_that(0).is_not_none()
assert_that(0).is_false()
assert_that(0).is_type_of(int)
assert_that(0).is_instance_of(int)

assert_that(0).is_zero()
assert_that(1).is_not_zero()
assert_that(1).is_positive()
assert_that(-1).is_negative()

assert_that(123).is_equal_to(123)
assert_that(123).is_not_equal_to(456)

assert_that(123).is_greater_than(100)
assert_that(123).is_greater_than_or_equal_to(123)
assert_that(123).is_less_than(200)
assert_that(123).is_less_than_or_equal_to(200)
assert_that(123).is_between(100, 200)
assert_that(123).is_close_to(100, 25)

assert_that(1).is_in(0,1,2,3)
assert_that(1).is_not_in(-1,-2,-3)
```

Matching floats:

```py
assert_that(0.0).is_not_none()
assert_that(0.0).is_false()
assert_that(0.0).is_type_of(float)
assert_that(0.0).is_instance_of(float)

assert_that(123.4).is_equal_to(123.4)
assert_that(123.4).is_not_equal_to(456.7)

assert_that(123.4).is_greater_than(100.1)
assert_that(123.4).is_greater_than_or_equal_to(123.4)
assert_that(123.4).is_less_than(200.2)
assert_that(123.4).is_less_than_or_equal_to(123.4)
assert_that(123.4).is_between(100.1, 200.2)
assert_that(123.4).is_close_to(123, 0.5)
```

Of course, using `is_equal_to()` with a `float` value is just asking for trouble. You'll always want to use the assertions methods like `is_close_to()` and `is_between()`.

### Lists

Matching lists:

```py
assert_that([]).is_not_none()
assert_that([]).is_empty()
assert_that([]).is_false()
assert_that([]).is_type_of(list)
assert_that([]).is_instance_of(list)

assert_that(['a','b']).is_length(2)
assert_that(['a','b']).is_not_empty()
assert_that(['a','b']).is_equal_to(['a','b'])
assert_that(['a','b']).is_not_equal_to(['b','a'])

assert_that(['a','b']).contains('a')
assert_that(['a','b']).contains('b','a')
assert_that(['a','b']).does_not_contain('x','y')
assert_that(['a','b','c']).contains_sequence('b','c')

assert_that(['a','x','x']).contains_duplicates()
assert_that(['a','b','c']).does_not_contain_duplicates()
```

### Tuples

Matching tuples:

```py
assert_that(()).is_not_none()
assert_that(()).is_empty()
assert_that(()).is_false()
assert_that(()).is_type_of(tuple)
assert_that(()).is_instance_of(tuple)

assert_that((1,2,3)).is_length(3)
assert_that((1,2,3)).is_not_empty()
assert_that((1,2,3)).is_equal_to((1,2,3))
assert_that((1,2,3)).is_not_equal_to((1,2,4))

assert_that((1,2,3)).contains(1)
assert_that((1,2,3)).contains(3,2,1)
assert_that((1,2,3)).does_not_contain(4,5,6)
assert_that((1,2,3)).contains_sequence(2,3)

assert_that((1,2,2)).contains_duplicates()
assert_that((1,2,3)).does_not_contain_duplicates()
```

### Dicts

Matching dicts:

```py
assert_that({}).is_not_none()
assert_that({}).is_empty()
assert_that({}).is_false()
assert_that({}).is_type_of(dict)
assert_that({}).is_instance_of(dict)

assert_that({'a':1,'b':2}).is_length(2)
assert_that({'a':1,'b':2}).is_not_empty()
assert_that({'a':1,'b':2}).is_equal_to({'a':1,'b':2})
assert_that({'a':1,'b':2}).is_equal_to({'b':2,'a':1})
assert_that({'a':1,'b':2}).is_not_equal_to({'a':1,'b':3})

assert_that({'a':1,'b':2}).contains('a')
assert_that({'a':1,'b':2}).contains('b','a')
assert_that({'a':1,'b':2}).does_not_contain('x')
assert_that({'a':1,'b':2}).does_not_contain('x','y')

# contains_key() is just an alias for contains()
assert_that({'a':1,'b':2}).contains_key('a')
assert_that({'a':1,'b':2}).contains_key('b','a')

# does_not_contain_key() is just an alias for does_not_contain()
assert_that({'a':1,'b':2}).does_not_contain_key('x')
assert_that({'a':1,'b':2}).does_not_contain_key('x','y')

assert_that({'a':1,'b':2}).contains_value(1)
assert_that({'a':1,'b':2}).contains_value(2,1)
assert_that({'a':1,'b':2}).does_not_contain_value(3)
assert_that({'a':1,'b':2}).does_not_contain_value(3,4)

assert_that({'a':1,'b':2}).contains_entry({'a':1})
assert_that({'a':1,'b':2}).contains_entry({'a':1},{'b':2})
```

### Sets

Matching sets:

```py
assert_that(set({})).is_not_none()
assert_that(set({})).is_empty()
assert_that(set({})).is_false()
assert_that(set({})).is_type_of(set)
assert_that(set({})).is_instance_of(set)

assert_that({'a','b'}).is_length(2)
assert_that({'a','b'}).is_not_empty()
assert_that({'a','b'}).is_equal_to({'a','b'})
assert_that({'a','b'}).is_equal_to({'b','a'})
assert_that({'a','b'}).is_not_equal_to({'a','x'})

assert_that({'a','b'}).contains('a')
assert_that({'a','b'}).contains('b','a')
assert_that({'a','b'}).does_not_contain('x','y')
```

### Booleans

Matching booleans:

```py
assert_that(True).is_true()
assert_that(False).is_false()
assert_that(True).is_type_of(bool)
```

### Dates

Matching dates:

```py
import datetime

today = datetime.datetime.today()
yesterday = today - datetime.timedelta(days=1)

assert_that(yesterday).is_before(today)
assert_that(today).is_after(yesterday)
```

You can also make assertions about date equality (ignoring various units of time) like this:

```py
today_0us = today - datetime.timedelta(microseconds=today.microsecond)
today_0s = today - datetime.timedelta(seconds=today.second)
today_0h = today - datetime.timedelta(hours=today.hour)

assert_that(today).is_equal_to_ignoring_milliseconds(today_0us)
assert_that(today).is_equal_to_ignoring_seconds(today_0s)
assert_that(today).is_equal_to_ignoring_time(today_0h)
assert_that(today).is_equal_to(today)
```

You can use these numeric assertions on dates:

```py
middle = today - datetime.timedelta(hours=12)
hours_24 = datetime.timedelta(hours=24)

assert_that(today).is_greater_than(yesterday)
assert_that(yesterday).is_less_than(today)
assert_that(middle).is_between(yesterday, today)

#note that the tolerance must be a datetime.timedelta object
assert_that(yesterday).is_close_to(today, hours_24)
```

Lastly, because of the dynamic assertions (see [Dynamic Assertions on Objects](#dynamic-assertions-on-objects) below) we can easily test the properties of a given date:

```py
# 1980-01-02 03:04:05.000006
x = datetime.datetime(1980, 1, 2, 3, 4, 5, 6)

assert_that(x).has_year(1980)
assert_that(x).has_month(1)
assert_that(x).has_day(2)
assert_that(x).has_hour(3)
assert_that(x).has_minute(4)
assert_that(x).has_second(5)
assert_that(x).has_microsecond(6)
```

Currently, `assertpy` only supports dates via the `datetime` type.

### Files

Matching files:

```py
assert_that('foo.txt').exists()
assert_that('foo.txt').is_file()

assert_that('mydir').exists()
assert_that('mydir').is_directory()

assert_that('foo.txt').is_named('foo.txt')
assert_that('foo.txt').is_child_of('mydir')
```

Matching file contents is done using the `contents_of()` helper to read the file into a string.  Then you can make quick work of it using the `assertpy` string assertions like this:

```py
from assertpy import assert_that, contents_of

assert_that(contents_of('foo.txt')).starts_with('foo').ends_with('bar').contains('oob')
```

### Objects

Matching an object:

```py
fred = Person('Fred','Smith')

assert_that(fred).is_not_none()
assert_that(fred).is_true()
assert_that(fred).is_type_of(Person)
assert_that(fred).is_instance_of(object)
```

Matching an attribute, a property, and a method:

```py
assert_that(fred.first_name).is_equal_to('Fred')
assert_that(fred.name).is_equal_to('Fred Smith')
assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')
```

Given `fred` is an instance of the following `Person` class:

```py
class Person(object):
    def __init__(self, first_name, last_name):
        self.first_name = first_name
        self.last_name = last_name

    @property
    def name(self):
        return '%s %s' % (self.first_name, self.last_name)

    def say_hello(self):
        return 'Hello, %s!' % self.first_name
```

#### Extracting Attributes from Objects

It is frequently necessary to test collections of objects.  The `assertpy` framework includes an `extract` method to flatten the collection on a given attribute, like this:

```py
fred = Person('Fred','Smith')
bob = Person('Bob','Barr')
people = [fred, bob]

assert_that(people).extract('first_name').is_equal_to(['Fred','Bob'])
assert_that(people).extract('first_name').contains('Fred','Bob')
assert_that(people).extract('first_name').does_not_contain('Charlie')
```

Of couse `extract` works with subclasses too...suppose we create a simple class hierarchy by creating a `Developer` subclass of `Person`, like this:

```py
class Developer(Person):
    def say_hello(self):
        return '%s writes code.' % self.first_name
```

Testing a mixed collection of parent and child objects works as expected:

```py
fred = Person('Fred','Smith')
joe = Developer('Joe','Coder')
people = [fred, joe]

assert_that(people).extract('first_name').contains('Fred','Joe')
```

Additionally, the `extract` method can accept a list of attributes to be extracted, in this case it returns a list of tuples:

```py
assert_that(people).extract('first_name', 'last_name').contains(('Fred','Smith'), ('Joe','Coder'))
```

Lastly, `extract` works on not just attributes, but also properties, and even zero-argument methods:

```py
assert_that(people).extract('name').contains('Fred Smith', 'Joe Coder')
assert_that(people).extract('say_hello').contains('Hello, Fred!', 'Joe writes code.')
```

#### Dynamic Assertions on Objects

When testing attribute of an object, the basic `assertpy` assertions can get a little verbose like this:

```py
fred = Person('Fred','Smith')

assert_that(fred.first_name).is_equal_to('Fred')
assert_that(fred.name).is_equal_to('Fred Smith')
assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')
```

So, `assertpy` takes advantage of the awesome dyanmism in the Python runtime to provide dynamic assertions in the form of `has_blah()` where `blah` is the name of any attribute, property, or zero-argument method on the given object.

Using dynamic assertions, we can rewrite the above assertions in a more compact and readable way like this:

```py
assert_that(fred).has_first_name('Fred')
assert_that(fred).has_name('Fred Smith')
assert_that(fred).has_say_hello('Hello, Fred!')
```

Since `fred` has the attribute `first_name`, the dynamic assertion method `has_first_name()` is available.  Similarly for the property `name` and the zero-argument method `say_hello()`.

### Failure

The `assertpy` framework includes a `fail()` method to explicitly force a test failure.  It can be used like this:

```py
from assertpy import assert_that,fail

class TestFailure(object):

    def test_fail(self):
        fail('forced failure')
```

A useful test pattern that requires the `fail()` method is to specifically verify the contents of an error message. For example:

```py
from assertpy import assert_that,fail

class TestFailure(object):

    def test_error_msg(self):
        try:
            some_func('bad arg')
            fail('should have raised error')
        except ValueError, ex:
            assert_that(ex.message).contains('some msg')
```

In the above code, we invoke `some_func()` with a bad argument which raises an exception.  The exception is then handled by the `try..except` block and the exact contents of the error message are verified.  Lastly, if an exception is not thrown by `some_func()` as expected, we fail the test via `fail()`.

This pattern is only used when you need to verify the contents of the error message.  If you only wish to check for an expected exception (and don't need to verify the error message itself), you're much better off using a test runner that supports expected exceptions.  [Nose](http://nose.readthedocs.org/) provides a [@raises](http://nose.readthedocs.org/en/latest/testing_tools.html#nose.tools.raises) decorator. [Pytest](http://pytest.org/latest/contents.html) has a [pytest.raises](http://pytest.org/latest/assert.html#assertions-about-expected-exceptions) method.

### Chaining

One of the nicest aspects of any fluent API is the ability to chain methods together.  In the case of `assertpy`, chaining allows you to write assertions as single statement -- that reads like a sentance, and is easy to understand.

Here are just a few examples:

```py
assert_that('foo').is_length(3).starts_with('f').ends_with('oo')
```

```py
assert_that([1,2,3]).is_type_of(list).contains(1,2).does_not_contain(4,5)
```

```py
assert_that(fred).has_first_name('Fred').has_last_name('Smith').has_shoe_size(12)
```

```py
assert_that(people).is_length(2).extract('first_name').contains('Fred','Joe')
```

## Future

The `assertpy` framework is already super useful, but there are always a few new features in the works...

If you'd like to help, check out the [open issues](https://github.com/ActivisionGameScience/assertpy/issues?q=is%3Aopen+is%3Aissue) and see our [Contributing](CONTRIBUTING.md) doc.

## History

#### v0.6 - Feb 2, 2015

- minor error message cleanups
- initial release on binstar

#### v0.5 - Jan 31, 2015

- initial release on PyPI

## License

All files are licensed under the BSD 3-Clause License as follows:
 
> Copyright (c) 2015, Activision Publishing, Inc.  
> All rights reserved.
> 
> Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
> 
> 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
>  
> 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
>  
> 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
>  
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
