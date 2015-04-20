# Copyright (c) 2015, Activision Publishing, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors
# may be used to endorse or promote products derived from this software without
# specific prior written permission.
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

__version__ = '0.7'

import re
import os
import datetime
import numbers

def assert_that(val):
    """Factory method for the assertion builder."""
    return AssertionBuilder(val)

def contents_of(f):
    """Helper to read the contents of the given file or path into a string."""
    if type(f) is str:
        with open(f, 'r') as fp:
            contents = fp.read()
    elif type(f) is file:
        contents = f.read()
    else:
        raise ValueError('val must be file or path, but was type <%s>' % type(f).__name__)
    return contents

def fail(msg = ''):
    """Force test failure with the given message."""
    if len(msg) == 0:
        raise AssertionError('Fail!')
    else:
        raise AssertionError('Fail: %s!' % msg)

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

    def is_length(self, length):
        """Asserts that val is the given length."""
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
                if type(self.val) is dict:
                    raise AssertionError('Expected <%s> to contain key <%s>, but did not.' % (self.val, items[0]))
                else:
                    raise AssertionError('Expected <%s> to contain item <%s>, but did not.' % (self.val, items[0]))
        else:
            for i in items:
                if i not in self.val:
                    if type(self.val) is dict:
                        raise AssertionError('Expected <%s> to contain keys %s, but did not contain key <%s>.' % (self.val, items, i))
                    else:
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

    def contains_sequence(self, *items):
        """Asserts that val contains the given sequence of items in order."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        else:
            try:
                for i in xrange(len(self.val) - len(items) + 1):
                    for j in xrange(len(items)):
                        if self.val[i+j] != items[j]:
                            break
                    else:
                        return self
            except TypeError:
                raise TypeError('val is not iterable')
        raise AssertionError('Expected <%s> to contain sequence %s, but did not.' % (self.val, items))

    def contains_duplicates(self):
        """Asserts that val is iterable and contains duplicate items."""
        try:
            if len(self.val) != len(set(self.val)):
                return self
        except TypeError:
            raise TypeError('val is not iterable')
        raise AssertionError('Expected <%s> to contain duplicates, but did not.' % self.val)

    def does_not_contain_duplicates(self):
        """Asserts that val is iterable and does not contain any duplicate items."""
        try:
            if len(self.val) == len(set(self.val)):
                return self
        except TypeError:
            raise TypeError('val is not iterable')
        raise AssertionError('Expected <%s> to not contain duplicates, but did.' % self.val)

    def is_empty(self):
        """Asserts that val is empty."""
        if len(self.val) != 0:
            if type(self.val) is str:
                raise AssertionError('Expected <%s> to be empty string, but was not.' % self.val)
            else:
                raise AssertionError('Expected <%s> to be empty, but was not.' % self.val)
        return self

    def is_not_empty(self):
        """Asserts that val is not empty."""
        if len(self.val) == 0:
            if type(self.val) is str:
                raise AssertionError('Expected not empty string, but was empty.')
            else:
                raise AssertionError('Expected not empty, but was empty.')
        return self

    def is_in(self, *items):
        """Asserts that val is equal to one of the given items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        else:
            for i in items:
                if self.val == i:
                    return self
        raise AssertionError('Expected <%s> to be in %s, but was not.' % (self.val, items))

    def is_not_in(self, *items):
        """Asserts that val is not equal to one of the given items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        else:
            for i in items:
                if self.val == i:
                    raise AssertionError('Expected <%s> to not be in %s, but was.' % (self.val, items))
        return self

### numeric assertions ###
    def _validate_numeric_or_datetime(self, other):
        if type(self.val) is complex or type(other) is complex:
            raise TypeError('ordering is not defined for complex numbers')
        if isinstance(self.val, numbers.Number) is False and type(self.val) is not datetime.datetime:
            raise TypeError('val is not numeric or datetime')
        if type(self.val) is datetime.datetime:
            if type(other) is not datetime.datetime:
                raise TypeError('given arg must be datetime, but was <%s>' % type(other).__name__)
        elif isinstance(other, numbers.Number) is False:
            raise TypeError('given arg must be numeric')

    def is_zero(self):
        """Asserts that val is numeric and equal to zero."""
        if isinstance(self.val, numbers.Number) is False:
            raise TypeError('val is not numeric')
        return self.is_equal_to(0)

    def is_not_zero(self):
        """Asserts that val is numeric and not equal to zero."""
        if isinstance(self.val, numbers.Number) is False:
            raise TypeError('val is not numeric')
        return self.is_not_equal_to(0)

    def is_greater_than(self, other):
        """Asserts that val is numeric and is greater than other."""
        self._validate_numeric_or_datetime(other)
        if self.val <= other:
            if type(self.val) is datetime.datetime:
                raise AssertionError('Expected <%s> to be greater than <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                raise AssertionError('Expected <%s> to be greater than <%s>, but was not.' % (self.val, other))
        return self

    def is_greater_than_or_equal_to(self, other):
        """Asserts that val is numeric and is greater than or equal to other."""
        self._validate_numeric_or_datetime(other)
        if self.val < other:
            if type(self.val) is datetime.datetime:
                raise AssertionError('Expected <%s> to be greater than or equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                raise AssertionError('Expected <%s> to be greater than or equal to <%s>, but was not.' % (self.val, other))
        return self

    def is_less_than(self, other):
        """Asserts that val is numeric and is less than other."""
        self._validate_numeric_or_datetime(other)
        if self.val >= other:
            if type(self.val) is datetime.datetime:
                raise AssertionError('Expected <%s> to be less than <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                raise AssertionError('Expected <%s> to be less than <%s>, but was not.' % (self.val, other))
        return self

    def is_less_than_or_equal_to(self, other):
        """Asserts that val is numeric and is less than or equal to other."""
        self._validate_numeric_or_datetime(other)
        if self.val > other:
            if type(self.val) is datetime.datetime:
                raise AssertionError('Expected <%s> to be less than or equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                raise AssertionError('Expected <%s> to be less than or equal to <%s>, but was not.' % (self.val, other))
        return self

    def is_positive(self):
        """Asserts that val is numeric and greater than zero."""
        return self.is_greater_than(0)

    def is_negative(self):
        """Asserts that val is numeric and less than zero."""
        return self.is_less_than(0)

    def is_between(self, low, high):
        """Asserts that val is numeric and is between low and high."""
        if type(self.val) is complex or type(low) is complex or type(high) is complex:
            raise TypeError('ordering is not defined for complex numbers')
        if isinstance(self.val, numbers.Number) is False and type(self.val) is not datetime.datetime:
            raise TypeError('val is not numeric or datetime')
        if type(self.val) is datetime.datetime:
            if type(low) is not datetime.datetime:
                raise TypeError('given low arg must be datetime, but was <%s>' % type(low).__name__)
            if type(high) is not datetime.datetime:
                raise TypeError('given high arg must be datetime, but was <%s>' % type(high).__name__)
        else:
            if isinstance(low, numbers.Number) is False:
                raise TypeError('given low arg must be numeric')
            if isinstance(high, numbers.Number) is False:
                raise TypeError('given high arg must be numeric')
        if low > high:
            raise ValueError('given low arg must be less than given high arg')
        if self.val < low or self.val > high:
            if type(self.val) is datetime.datetime:
                raise AssertionError('Expected <%s> to be between <%s> and <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), low.strftime('%Y-%m-%d %H:%M:%S'), high.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                raise AssertionError('Expected <%s> to be between <%s> and <%s>, but was not.' % (self.val, low, high))
        return self

    def is_close_to(self, other, tolerance):
        """Asserts that val is numeric and is close to other within tolerance."""
        if type(self.val) is complex or type(other) is complex or type(tolerance) is complex:
            raise TypeError('ordering is not defined for complex numbers')
        if isinstance(self.val, numbers.Number) is False and type(self.val) is not datetime.datetime:
            raise TypeError('val is not numeric or datetime')
        if type(self.val) is datetime.datetime:
            if type(other) is not datetime.datetime:
                raise TypeError('given arg must be datetime, but was <%s>' % type(other).__name__)
            if type(tolerance) is not datetime.timedelta:
                raise TypeError('given tolerance arg must be timedelta, but was <%s>' % type(tolerance).__name__)
        else:
            if isinstance(other, numbers.Number) is False:
                raise TypeError('given arg must be numeric')
            if isinstance(tolerance, numbers.Number) is False:
                raise TypeError('given tolerance arg must be numeric')
            if tolerance < 0:
                raise ValueError('given tolerance arg must be positive')
        if self.val < (other-tolerance) or self.val > (other+tolerance):
            if type(self.val) is datetime.datetime:
                h, rem = divmod(tolerance.total_seconds(), 3600)
                m, s = divmod(rem, 60)
                raise AssertionError('Expected <%s> to be close to <%s> within tolerance <%d:%02d:%02d>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S'), h, m, s))
            else:
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

    def is_alpha(self):
        """Asserts that val is non-empty string and all characters are alphabetic."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if len(self.val) == 0:
            raise ValueError('val is empty')
        if not self.val.isalpha():
            raise AssertionError('Expected <%s> to contain only alphabetic chars, but did not.' % self.val)
        return self

    def is_digit(self):
        """Asserts that val is non-empty string and all characters are digits."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if len(self.val) == 0:
            raise ValueError('val is empty')
        if not self.val.isdigit():
            raise AssertionError('Expected <%s> to contain only digits, but did not.' % self.val)
        return self

    def is_lower(self):
        """Asserts that val is non-empty string and all characters are lowercase."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if len(self.val) == 0:
            raise ValueError('val is empty')
        if self.val != self.val.lower():
            raise AssertionError('Expected <%s> to contain only lowercase chars, but did not.' % self.val)
        return self

    def is_upper(self):
        """Asserts that val is non-empty string and all characters are uppercase."""
        if type(self.val) is not str:
            raise TypeError('val is not a string')
        if len(self.val) == 0:
            raise ValueError('val is empty')
        if self.val != self.val.upper():
            raise AssertionError('Expected <%s> to contain only uppercase chars, but did not.' % self.val)
        return self

    def is_unicode(self):
        """Asserts that val is a unicode string."""
        if type(self.val) is not unicode:
            raise AssertionError('Expected <%s> to be unicode, but was <%s>.' % (self.val, type(self.val).__name__))
        return self

### dict assertions ###
    def contains_key(self, *keys):
        """Asserts the val is a dict and contains the given key or keys.  Alias for contains()."""
        if type(self.val) is not dict:
            raise TypeError('val is not a dict')
        return self.contains(*keys)

    def does_not_contain_key(self, *keys):
        """Asserts the val is a dict and does not contain the given key or keys.  Alias for does_not_contain()."""
        if type(self.val) is not dict:
            raise TypeError('val is not a dict')
        return self.does_not_contain(*keys)

    def contains_value(self, *values):
        """Asserts that val is a dict and contains the given value or values."""
        if type(self.val) is not dict:
            raise TypeError('val is not a dict')
        if len(values) == 0:
            raise ValueError('one or more value args must be given')
        for v in values:
            if v not in self.val.values():
                raise AssertionError('Expected <%s> to contain value <%s>, but did not.' % (self.val, v))
        return self

    def does_not_contain_value(self, *values):
        """Asserts that val is a dict and does not contain the given value or values."""
        if type(self.val) is not dict:
            raise TypeError('val is not a dict')
        if len(values) == 0:
            raise ValueError('one or more value args must be given')
        elif len(values) == 1:
            if values[0] in self.val.values():
                raise AssertionError('Expected <%s> to not contain value <%s>, but did.' % (self.val, values[0]))
        else:
            for v in values:
                if v in self.val.values():
                    raise AssertionError('Expected <%s> to not contain values %s, but did contain <%s>.' % (self.val, values, v))
        return self

    def contains_entry(self, *entries):
        """Asserts that val is a dict and contains the given entry or entries."""
        if type(self.val) is not dict:
            raise TypeError('val is not a dict')
        if len(entries) == 0:
            raise ValueError('one or more entry args must be given')
        for e in entries:
            if type(e) is not dict:
                raise TypeError('given entry arg must be a dict')
            if len(e) != 1:
                raise ValueError('given entry args must contain exactly one key-value pair')
            k = e.keys()[0]
            if k not in self.val:
                raise AssertionError('Expected <%s> to contain entry %s, but did not contain key <%s>.' % (self.val, e, k))
            elif self.val[k] != e[k]:
                raise AssertionError('Expected <%s> to contain entry %s, but key <%s> did not contain value <%s>.' % (self.val, e, k, e[k]))
        return self

    def does_not_contain_entry(self, *entries):
        """Asserts that val is a dict and does not contain the given entry or entries."""
        if type(self.val) is not dict:
            raise TypeError('val is not a dict')
        if len(entries) == 0:
            raise ValueError('one or more entry args must be given')
        for e in entries:
            if type(e) is not dict:
                raise TypeError('given entry arg must be a dict')
            if len(e) != 1:
                raise ValueError('given entry args must contain exactly one key-value pair')
            k = e.keys()[0]
            if k in self.val and e[k] == self.val[k]:
                raise AssertionError('Expected <%s> to not contain entry %s, but did.' % (self.val, e))
        return self

### datetime assertions ###
    def is_before(self, other):
        """Asserts that val is a date and is before other date."""
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val >= other:
            raise AssertionError('Expected <%s> to be before <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
        return self

    def is_after(self, other):
        """Asserts that val is a date and is after other date."""
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val <= other:
            raise AssertionError('Expected <%s> to be after <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
        return self

    def is_equal_to_ignoring_milliseconds(self, other):
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val.date() != other.date() or self.val.hour != other.hour or self.val.minute != other.minute or self.val.second != other.second:
            raise AssertionError('Expected <%s> to be equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
        return self

    def is_equal_to_ignoring_seconds(self, other):
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val.date() != other.date() or self.val.hour != other.hour or self.val.minute != other.minute:
            raise AssertionError('Expected <%s> to be equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M'), other.strftime('%Y-%m-%d %H:%M')))
        return self

    def is_equal_to_ignoring_time(self, other):
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val.date() != other.date():
            raise AssertionError('Expected <%s> to be equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d'), other.strftime('%Y-%m-%d')))
        return self

### file assertions ###
    def exists(self):
        """Asserts that val is a path and that it exists."""
        if type(self.val) is not str:
            raise TypeError('val is not a path')
        if not os.path.exists(self.val):
            raise AssertionError('Expected <%s> to exist, but not found.' % self.val)
        return self

    def is_file(self):
        """Asserts that val is an existing path to a file."""
        self.exists()
        if not os.path.isfile(self.val):
            raise AssertionError('Expected <%s> to be a file, but was not.' % self.val)
        return self

    def is_directory(self):
        """Asserts that val is an existing path to a directory."""
        self.exists()
        if not os.path.isdir(self.val):
            raise AssertionError('Expected <%s> to be a directory, but was not.' % self.val)
        return self

    def is_named(self, filename):
        """Asserts that val is an existing path to a file and that file is named filename."""
        self.is_file()
        if type(filename) is not str:
            raise TypeError('given filename arg must be a path')
        val_filename = os.path.basename(os.path.abspath(self.val))
        if val_filename != filename:
            raise AssertionError('Expected filename <%s> to be equal to <%s>, but was not.' % (val_filename, filename))
        return self

    def is_child_of(self, parent):
        """Asserts that val is an existing path to a file and that file is a child of parent."""
        self.is_file()
        if type(parent) is not str:
            raise TypeError('given parent directory arg must be a path')
        val_abspath = os.path.abspath(self.val)
        parent_abspath = os.path.abspath(parent)
        if not val_abspath.startswith(parent_abspath):
            raise AssertionError('Expected file <%s> to be a child of <%s>, but was not.' % (val_abspath, parent_abspath))
        return self

### collection of objects assertions ###
    def extract(self, *names):
        """Asserts that val is collection, then extracts the named properties or named zero-arg methods into a list (or list of tuples if multiple names are given)."""
        if type(self.val) not in [list, tuple, set]:
            raise TypeError('val is not a collection')
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
                            raise ValueError('val method <%s()> exists, but is not zero-arg method' % name)
                    else:
                        items.append(attr)
                else:
                    raise ValueError('val does not have property or zero-arg method <%s>' % name)
            extracted.append(tuple(items) if len(items) > 1 else items[0])
        return AssertionBuilder(extracted)

### dynamic assertions ###
    def __getattr__(self, attr):
        """Asserts that val has attribute attr and that attribute's value is equal to other via a dynamic assertion of the form: has_<attr>()."""
        if not attr.startswith('has_'):
            raise AttributeError('assertpy has no assertion <%s()>' % attr)

        attr_name = attr[4:]
        if not hasattr(self.val, attr_name):
            raise AttributeError('val has no attribute <%s>' % attr_name)

        def _wrapper(*args, **kwargs):
            if len(args) != 1:
                raise TypeError('assertion <%s()> takes exactly 1 argument (%d given)' % (attr, len(args)))
            other = args[0]
            val_attr = getattr(self.val, attr_name)

            if callable(val_attr):
                try:
                    val = val_attr()
                except TypeError:
                    raise TypeError('val does not have zero-arg method <%s()>' % attr_name)
            else:
                val = val_attr

            if val != other:
                raise AssertionError('Expected <%s> to be equal to <%s>, but was not.' % (val, other))
            return self
        return _wrapper
