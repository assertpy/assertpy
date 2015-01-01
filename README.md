# assertpy

Dead simple assertions framework for unit testing in Python with a nice fluent API.

[![Build Status](https://travis-ci.org/ActivisionGameScience/assertpy.svg?branch=master)](https://travis-ci.org/ActivisionGameScience/assertpy)
[![Coverage Status](https://coveralls.io/repos/ActivisionGameScience/assertpy/badge.png)](https://coveralls.io/r/ActivisionGameScience/assertpy)

## Usage

Just import the `assert_that` function, and away you go...

```py
from assertpy import assert_that

class TestSomething(object):

    def testSomething(self):
        assert_that('something').is_length(9).is_equal_to('something')
```

## The API

The fluent API of `assertpy` is designed to create compact, yet readable tests.
The API has been modeled after other fluent testing APIs, especially the awesome 
[AssertJ](http://joel-costigliola.github.io/assertj/) assertion framework for Java.  Of course, in `assertpy` everything is fully pythonic and designed to take full advantage of the dynamism in the Python runtime.

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
assert_that('foo').is_equal_to('foo')
assert_that('foo').is_not_equal_to('bar')
assert_that('foo').is_equal_to_ignoring_case('FOO')

assert_that('foo').contains('f')
assert_that('foo').contains('f','oo')
assert_that('foo').does_not_contain('x')

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

assert_that(123).is_equal_to(123)
assert_that(123).is_not_equal_to(456)

assert_that(123).is_greater_than(100)
assert_that(123).is_less_than(200)
assert_that(123).is_between(100, 200)
assert_that(123).is_close_to(100, 25)
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
assert_that(123.4).is_less_than(200.2)
assert_that(123.4).is_between(100.1, 200.2)
assert_that(123.4).is_close_to(123, 0.5)
```

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
assert_that({'a':1,'b':2}).does_not_contain('x','y')

assert_that({'a':1,'b':2}).contains_value(1)
assert_that({'a':1,'b':2}).contains_value(2,1)

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

### Classes

Matching classes:

```py
fred = Person('Fred','Smith')

assert_that(fred).is_not_none()
assert_that(fred).is_true()
assert_that(fred).is_type_of(Person)
assert_that(fred).is_instance_of(object)

assert_that(fred.first_name).is_equal_to('Fred')
assert_that(fred.name).is_equal_to('Fred Smith')
assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')
```

Given the `Person` class:

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

When testing a collection of objects, use the `extract` method to flatten the collection on a given attribute, like this:

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
assert_that(people).extract('first_name', 'name').contains(('Fred','Fred Smith'), ('Joe','Joe Coder'))
```

Lastly, `extract` can accept zero-argument methods as if they were attributes:

```py
assert_that(people).extract('say_hello').contains('Hello, Fred!', 'Joe writes code.')
```

### Chaining

One of the nicest aspects of any fluent API is the ability to chain methods together.  In the case of `assertpy`, chaining allows you to  assertions into a single statement -- that reads like a sentance, and is easy to understand.

Here are just a few examples:

```py
assert_that('foo').is_length(3).starts_with('f').ends_with('oo')
```

```py
assert_that([1,2,3]).is_type_of(list).contains(1,2).does_not_contain(4,5)
```

```py
assert_that(people).is_length(2).extract('first_name').contains('Fred','Joe')
```

## Future

The `assertpy` framework is already super useful, but there is still lots of work to do:

1. **packaging** - get everything packaged and uploaded to PyPI
1. **Dates** - support for assertions around dates and times
1. **Files** - support for file assertions, including file metadata and file contents
1. **Classes** - dynamic assertion methods about class attributes
1. Lots more...

If you'd like to help, check out the [open issues](https://github.com/ActivisionGameScience/assertpy/issues?q=is%3Aopen+is%3Aissue) and see our [Contributing](CONTRIBUTING.md) doc.

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
