# Copyright (c) 2015, Activision Publishing, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice, this
# list of conditions and the following disclaimer in the documentation and/or
# other materials provided with the distribution.
#
# * Neither the name of the Activision Publishing, Inc. nor the names of its
# contributors may be used to endorse or promote products derived from this
# software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Fluent assertion framework for better, more readable tests."""

import re

def assert_that(val):
    """Factory method for the assertion builder."""
    return AssertionBuilder(val)

class AssertionBuilder(object):
    """Assertion builder."""

    def __init__(self, val):
        """Construct the assertion builder."""
        self.val = val

    def is_equal_to(self, other):
        """Asserts that val is equal to other."""
        if self.val != other:
            raise AssertionError('Expected <%s> to be equal to <%s>, but was not.' % (self.val, other))
        return self

    def is_not_equal_to(self, other):
        """Asserts that val is not equal to other."""
        if self.val == other:
            raise AssertionError('Expected <%s> to be not equal to <%s>, but was.' % (self.val, other))
        return self

    def is_true(self):
        """Asserts that val is true."""
        if not self.val:
            raise AssertionError('Expected <True>, but was not.')
        return self

    def is_false(self):
        """Asserts that val is false."""
        if self.val:
            raise AssertionError('Expected <False>, but was not.')
        return self

    def is_none(self):
        """Asserts that val is none."""
        if self.val is not None:
            raise AssertionError('Expected <%s> to be <None>, but was not.' % self.val)
        return self

    def is_not_none(self):
        """Asserts that val is not none."""
        if self.val is None:
            raise AssertionError('Expected not <None>, but was.')
        return self

    def is_type_of(self, some_type):
        """Asserts that val is of the given type."""
        if type(some_type) is not type:
            raise TypeError('given arg must be a type')
        if type(self.val) is not some_type:
            if hasattr(self.val, '__name__'):
                t = self.val.__name__
            elif hasattr(self.val, '__class__'):
                t = self.val.__class__.__name__
            else:
                t = 'unknown'
            raise AssertionError('Expected <%s:%s> to be of type <%s>, but was not.' % (self.val, t, some_type.__name__))
        return self

    def is_instance_of(self, some_class):
        """Asserts that val is an instance of the given class."""
        if type(some_class) is not type:
            raise TypeError('given arg must be a class')
        if not isinstance(self.val, some_class):
            if hasattr(self.val, '__name__'):
                t = self.val.__name__
            elif hasattr(self.val, '__class__'):
                t = self.val.__class__.__name__
            else:
                t = 'unknown'
            raise AssertionError('Expected <%s:%s> to be instance of class <%s>, but was not.' % (self.val, t, some_class.__name__))
        return self

    def has_length(self, length):
        """Asserts that val has given length."""
        if type(length) is not int:
            raise TypeError('given arg must be an int')
        if length < 0:
            raise ValueError('given arg must be a positive int')
        if len(self.val) != length:
            raise AssertionError('Expected <%s> to be of length <%d>, but was <%d>.' % (self.val, length, len(self.val)))
        return self

    def contains(self, *items):
        """Asserts that val contains the given item or items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        elif len(items) == 1:
            if items[0] not in self.val:
                raise AssertionError('Expected <%s> to contain item <%s>, but did not.' % (self.val, items[0]))
        else:
            for i in items:
                if i not in self.val:
                    raise AssertionError('Expected <%s> to contain items %s, but did not contain <%s>.' % (self.val, items, i))
        return self

    def does_not_contain(self, *items):
        """Asserts that val does not contain the given item or items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        elif len(items) == 1:
            if items[0] in self.val:
                raise AssertionError('Expected <%s> to not contain item <%s>, but did.' % (self.val, items[0]))
        else:
            for i in items:
                if i in self.val:
                    raise AssertionError('Expected <%s> to not contain items %s, but did contain <%s>.' % (self.val, items, i))
        return self

    def is_empty(self):
        """Asserts that val is empty."""
        if len(self.val) != 0:
            raise AssertionError('Expected <%s> to be empty%s, but was not.' % (self.val, ' string' if type(self.val) is str else ''))
        return self

    def is_not_empty(self):
        """Asserts that val is not empty."""
        if type(self.val) is str:
            if len(self.val) == 0:
                raise AssertionError('Expected not empty string, but was empty.')
        else:
            if len(self.val) == 0:
                raise AssertionError('Expected not empty, but was empty.')
        return self

### numeric assertions ###
    def is_greater_than(self, other):
        """Asserts that val is numeric and is greater than other."""
        if type(self.val) is complex or type(other) is complex:
            raise TypeError('ordering is not defined for complex numbers')
        if type(self.val) not in (int, float, long):
            raise TypeError('val is not numeric')
        if type(other) not in (int, float, long):
            raise TypeError('given arg must be numeric')
        if self.val <= other:
            raise AssertionError('Expected <%s> to be greater than <%s>, but was not.' % (self.val, other))
        return self

    def is_less_than(self, other):
        """Asserts that val is numeric and is less than other."""
        if type(self.val) is complex or type(other) is complex:
            raise TypeError('ordering is not defined for complex numbers')
        if type(self.val) not in (int, float, long):
            raise TypeError('val is not numeric')
        if type(other) not in (int, float, long):
            raise TypeError('given arg must be numeric')
        if self.val >= other:
            raise AssertionError('Expected <%s> to be less than <%s>, but was not.' % (self.val, other))
        return self

    def is_between(self, low, high):
        """Asserts that val is numeric and is between low and high."""
        if type(self.val) is complex or type(low) is complex or type(high) is complex:
            raise TypeError('ordering is not defined for complex numbers')
        if type(self.val) not in (int, float, long):
            raise TypeError('val is not numeric')
        if type(low) not in (int, float, long):
            raise TypeError('given low arg must be numeric')
        if type(high) not in (int, float, long):
            raise TypeError('given high arg must be numeric')
        if low > high:
            raise ValueError('given low arg must be less than given high arg')
        if self.val < low or self.val > high:
            raise AssertionError('Expected <%s> to be between <%s> and <%s>, but was not.' % (self.val, low, high))
        return self

    def is_close_to(self, other, tolerance):
        """Asserts that val is numeric and is close to other within tolerance."""
        if type(self.val) is complex or type(other) is complex or type(tolerance) is complex:
            raise TypeError('ordering is not defined for complex numbers')
        if type(self.val) not in (int, float, long):
            raise TypeError('val is not numeric')
        if type(other) not in (int, float, long):
            raise TypeError('given arg must be numeric')
        if type(tolerance) not in (int, float, long):
            raise TypeError('given tolerance arg must be numeric')
        if tolerance < 0:
            raise ValueError('given tolerance arg must be positive')
        if self.val < (other-tolerance) or self.val > (other+tolerance):
            raise AssertionError('Expected <%s> to be close to <%s> within tolerance <%s>, but was not.' % (self.val, other, tolerance))
        return self

### string assertions ###
    def is_equal_to_ignoring_case(self, other):
        """Asserts that val is case-insensitive equal to other."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if type(other) is not str:
            raise TypeError('given arg must be a string')
        if self.val.lower() != other.lower():
            raise AssertionError('Expected <%s> to be case-insensitive equal to <%s>, but was not.' % (self.val, other))
        return self

    def starts_with(self, prefix):
        """Asserts that val is string and starts with prefix."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if type(prefix) is not str:
            raise TypeError('given prefix arg must be a string')
        if len(prefix) == 0:
            raise ValueError('given prefix arg must not be empty')
        if not self.val.startswith(prefix):
            raise AssertionError('Expected <%s> to start with <%s>, but did not.' % (self.val, prefix))
        return self

    def ends_with(self, suffix):
        """Asserts that val is string and ends with suffix."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if type(suffix) is not str:
            raise TypeError('given suffix arg must be a string')
        if len(suffix) == 0:
            raise ValueError('given suffix arg must not be empty')
        if not self.val.endswith(suffix):
            raise AssertionError('Expected <%s> to end with <%s>, but did not.' % (self.val, suffix))
        return self

    def matches(self, pattern):
        """Asserts that val is string and matches regex pattern."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if type(pattern) is not str:
            raise TypeError('given pattern arg must be a string')
        if len(pattern) == 0:
            raise ValueError('given pattern arg must not be empty')
        if re.search(pattern, self.val) is None:
            raise AssertionError('Expected <%s> to match pattern <%s>, but did not.' % (self.val, pattern))
        return self

    def does_not_match(self, pattern):
        """Asserts that val is string and does not match regex pattern."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if type(pattern) is not str:
            raise TypeError('given pattern arg must be a string')
        if len(pattern) == 0:
            raise ValueError('given pattern arg must not be empty')
        if re.search(pattern, self.val) is not None:
            raise AssertionError('Expected <%s> to not match pattern <%s>, but did.' % (self.val, pattern))
        return self

### dict assertions ###
    def contains_value(self, *values):
        """Asserts that val is a dict and contains the given value or values."""
        if type(self.val) is not dict:
            raise TypeError('val is not dict')
        if len(values) == 0:
            raise ValueError('one or more value args must be given')
        for v in values:
            if v not in self.val.values():
                raise AssertionError('Expected <%s> to contain value <%s>, but did not.' % (self.val, v))
        return self

    def contains_entry(self, *entries):
        """Asserts that val is a dict and contains the given entry or entries."""
        if type(self.val) is not dict:
            raise TypeError('val is not dict')
        if len(entries) == 0:
            raise ValueError('one or more entry args must be given')
        for e in entries:
            if type(e) is not dict:
                raise TypeError('given entry arg must be dict')
            if len(e) != 1:
                raise ValueError('given entry args must contain exactly one key-value pair')
            k = e.keys()[0]
            if k not in self.val:
                raise AssertionError('Expected <%s> to contain entry %s, but did not contain key <%s>.' % (self.val, e, k))
            elif self.val[k] != e[k]:
                raise AssertionError('Expected <%s> to contain entry %s, but key <%s> did not contain value <%s>.' % (self.val, e, k, e[k]))
        return self

    def extract(self, *names):
        """Asserts that val is collection, then extracts the named properties or named zero-arg methods into a list (or list of tuples if multiple names are given)."""
        if type(self.val) not in [list, tuple, set]:
            raise TypeError('val is not collection')
        if len(names) == 0:
            raise ValueError('one or more name args must be given')
        extracted = []
        for i in self.val:
            items = []
            for name in names:
                if hasattr(i, name):
                    attr = getattr(i, name)
                    if callable(attr):
                        try:
                            items.append(attr())
                        except TypeError:
                            raise ValueError('val does not have zero-arg method <%s()>' % name)
                    else:
                        items.append(attr)
                else:
                    raise ValueError('val does not have property or zero-arg method <%s>' % name)
            extracted.append(tuple(items) if len(items) > 1 else items[0])
        return AssertionBuilder(extracted)
