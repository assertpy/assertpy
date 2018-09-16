# Copyright (c) 2015-2018, Activision Publishing, Inc.
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

"""Assertion library for python unit testing with a fluent API"""

from __future__ import division, print_function
import re
import os
import sys
import datetime
import numbers
import collections
import inspect
import math
import contextlib
import json

__version__ = '0.14'

__tracebackhide__ = True # clean tracebacks via py.test integration
contextlib.__tracebackhide__ = True # monkey patch contextlib with clean py.test tracebacks

if sys.version_info[0] == 3:
    str_types = (str,)
    xrange = range
    unicode = str
else:
    str_types = (basestring,)
    xrange = xrange
    unicode = unicode


### soft assertions ###
_soft_ctx = False
_soft_err = []

@contextlib.contextmanager
def soft_assertions():
    global _soft_ctx
    global _soft_err

    # init ctx
    _soft_ctx = True
    _soft_err = []

    try:
        yield
    finally:
        # reset ctx
        _soft_ctx = False

    if _soft_err:
        out = 'soft assertion failures:'
        for i,msg in enumerate(_soft_err):
            out += '\n%d. %s' % (i+1, msg)
        # reset msg, then raise
        _soft_err = []
        raise AssertionError(out)


### factory methods ###
def assert_that(val, description=''):
    """Factory method for the assertion builder with value to be tested and optional description."""
    global _soft_ctx
    if _soft_ctx:
        return AssertionBuilder(val, description, 'soft')
    return AssertionBuilder(val, description)

def assert_warn(val, description=''):
    """Factory method for the assertion builder with value to be tested, optional description, and
       just warn on assertion failures instead of raisings exceptions."""
    return AssertionBuilder(val, description, 'warn')

def contents_of(f, encoding='utf-8'):
    """Helper to read the contents of the given file or path into a string with the given encoding.
    Encoding defaults to 'utf-8', other useful encodings are 'ascii' and 'latin-1'."""

    try:
        contents = f.read()
    except AttributeError:
        try:
            with open(f, 'r') as fp:
                contents = fp.read()
        except TypeError:
            raise ValueError('val must be file or path, but was type <%s>' % type(f).__name__)
        except OSError:
            if not isinstance(f, str_types):
                raise ValueError('val must be file or path, but was type <%s>' % type(f).__name__)
            raise

    if sys.version_info[0] == 3 and type(contents) is bytes:
        # in PY3 force decoding of bytes to target encoding
        return contents.decode(encoding, 'replace')
    elif sys.version_info[0] == 2 and encoding == 'ascii':
        # in PY2 force encoding back to ascii
        return contents.encode('ascii', 'replace')
    else:
        # in all other cases, try to decode to target encoding
        try:
            return contents.decode(encoding, 'replace')
        except AttributeError:
            pass
    # if all else fails, just return the contents "as is"
    return contents

def fail(msg=''):
    """Force test failure with the given message."""
    raise AssertionError('Fail: %s!' % msg if msg else 'Fail!')

def soft_fail(msg=''):
    """Adds error message to soft errors list if within soft assertions context.
       Either just force test failure with the given message."""
    global _soft_ctx
    if _soft_ctx:
        global _soft_err
        _soft_err.append('Fail: %s!' % msg if msg else 'Fail!')
        return
    fail(msg)


class AssertionBuilder(object):
    """Assertion builder."""

    def __init__(self, val, description='', kind=None, expected=None):
        """Construct the assertion builder."""
        self.val = val
        self.description = description
        self.kind = kind
        self.expected = expected

    def described_as(self, description):
        """Describes the assertion.  On failure, the description is included in the error message."""
        self.description = str(description)
        return self

    def is_equal_to(self, other, **kwargs):
        """Asserts that val is equal to other."""
        if self._check_dict_like(self.val, check_values=False, return_as_bool=True) and self._check_dict_like(other, check_values=False, return_as_bool=True):
            if self._dict_not_equal(self.val, other, ignore=kwargs.get('ignore'), include=kwargs.get('include')):
                self._dict_err(self.val, other, ignore=kwargs.get('ignore'), include=kwargs.get('include'))
        else:
            if self.val != other:
                self._err('Expected <%s> to be equal to <%s>, but was not.' % (self.val, other))
        return self

    def is_not_equal_to(self, other):
        """Asserts that val is not equal to other."""
        if self.val == other:
            self._err('Expected <%s> to be not equal to <%s>, but was.' % (self.val, other))
        return self

    def is_same_as(self, other):
        """Asserts that the val is identical to other, via 'is' compare."""
        if self.val is not other:
            self._err('Expected <%s> to be identical to <%s>, but was not.' % (self.val, other))
        return self

    def is_not_same_as(self, other):
        """Asserts that the val is not identical to other, via 'is' compare."""
        if self.val is other:
            self._err('Expected <%s> to be not identical to <%s>, but was.' % (self.val, other))
        return self

    def is_true(self):
        """Asserts that val is true."""
        if not self.val:
            self._err('Expected <True>, but was not.')
        return self

    def is_false(self):
        """Asserts that val is false."""
        if self.val:
            self._err('Expected <False>, but was not.')
        return self

    def is_none(self):
        """Asserts that val is none."""
        if self.val is not None:
            self._err('Expected <%s> to be <None>, but was not.' % self.val)
        return self

    def is_not_none(self):
        """Asserts that val is not none."""
        if self.val is None:
            self._err('Expected not <None>, but was.')
        return self

    def is_type_of(self, some_type):
        """Asserts that val is of the given type."""
        if type(some_type) is not type and\
                not issubclass(type(some_type), type):
            raise TypeError('given arg must be a type')
        if type(self.val) is not some_type:
            if hasattr(self.val, '__name__'):
                t = self.val.__name__
            elif hasattr(self.val, '__class__'):
                t = self.val.__class__.__name__
            else:
                t = 'unknown'
            self._err('Expected <%s:%s> to be of type <%s>, but was not.' % (self.val, t, some_type.__name__))
        return self

    def is_instance_of(self, some_class):
        """Asserts that val is an instance of the given class."""
        try:
            if not isinstance(self.val, some_class):
                if hasattr(self.val, '__name__'):
                    t = self.val.__name__
                elif hasattr(self.val, '__class__'):
                    t = self.val.__class__.__name__
                else:
                    t = 'unknown'
                self._err('Expected <%s:%s> to be instance of class <%s>, but was not.' % (self.val, t, some_class.__name__))
        except TypeError:
            raise TypeError('given arg must be a class')
        return self

    def is_length(self, length):
        """Asserts that val is the given length."""
        if type(length) is not int:
            raise TypeError('given arg must be an int')
        if length < 0:
            raise ValueError('given arg must be a positive int')
        if len(self.val) != length:
            self._err('Expected <%s> to be of length <%d>, but was <%d>.' % (self.val, length, len(self.val)))
        return self

    def contains(self, *items):
        """Asserts that val contains the given item or items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        elif len(items) == 1:
            if items[0] not in self.val:
                if self._check_dict_like(self.val, return_as_bool=True):
                    self._err('Expected <%s> to contain key <%s>, but did not.' % (self.val, items[0]))
                else:
                    self._err('Expected <%s> to contain item <%s>, but did not.' % (self.val, items[0]))
        else:
            missing = []
            for i in items:
                if i not in self.val:
                    missing.append(i)
            if missing:
                if self._check_dict_like(self.val, return_as_bool=True):
                    self._err('Expected <%s> to contain keys %s, but did not contain key%s %s.' % (self.val, self._fmt_items(items), '' if len(missing) == 0 else 's', self._fmt_items(missing)))
                else:
                    self._err('Expected <%s> to contain items %s, but did not contain %s.' % (self.val, self._fmt_items(items), self._fmt_items(missing)))
        return self

    def does_not_contain(self, *items):
        """Asserts that val does not contain the given item or items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        elif len(items) == 1:
            if items[0] in self.val:
                self._err('Expected <%s> to not contain item <%s>, but did.' % (self.val, items[0]))
        else:
            found = []
            for i in items:
                if i in self.val:
                    found.append(i)
            if found:
                self._err('Expected <%s> to not contain items %s, but did contain %s.' % (self.val, self._fmt_items(items), self._fmt_items(found)))
        return self

    def contains_only(self, *items):
        """Asserts that val contains only the given item or items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        else:
            extra = []
            for i in self.val:
                if i not in items:
                    extra.append(i)
            if extra:
                self._err('Expected <%s> to contain only %s, but did contain %s.' % (self.val, self._fmt_items(items), self._fmt_items(extra)))

            missing = []
            for i in items:
                if i not in self.val:
                    missing.append(i)
            if missing:
                self._err('Expected <%s> to contain only %s, but did not contain %s.' % (self.val, self._fmt_items(items), self._fmt_items(missing)))
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
        self._err('Expected <%s> to contain sequence %s, but did not.' % (self.val, self._fmt_items(items)))

    def contains_duplicates(self):
        """Asserts that val is iterable and contains duplicate items."""
        try:
            if len(self.val) != len(set(self.val)):
                return self
        except TypeError:
            raise TypeError('val is not iterable')
        self._err('Expected <%s> to contain duplicates, but did not.' % self.val)

    def does_not_contain_duplicates(self):
        """Asserts that val is iterable and does not contain any duplicate items."""
        try:
            if len(self.val) == len(set(self.val)):
                return self
        except TypeError:
            raise TypeError('val is not iterable')
        self._err('Expected <%s> to not contain duplicates, but did.' % self.val)

    def is_empty(self):
        """Asserts that val is empty."""
        if len(self.val) != 0:
            if isinstance(self.val, str_types):
                self._err('Expected <%s> to be empty string, but was not.' % self.val)
            else:
                self._err('Expected <%s> to be empty, but was not.' % self.val)
        return self

    def is_not_empty(self):
        """Asserts that val is not empty."""
        if len(self.val) == 0:
            if isinstance(self.val, str_types):
                self._err('Expected not empty string, but was empty.')
            else:
                self._err('Expected not empty, but was empty.')
        return self

    def is_in(self, *items):
        """Asserts that val is equal to one of the given items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        else:
            for i in items:
                if self.val == i:
                    return self
        self._err('Expected <%s> to be in %s, but was not.' % (self.val, self._fmt_items(items)))

    def is_not_in(self, *items):
        """Asserts that val is not equal to one of the given items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        else:
            for i in items:
                if self.val == i:
                    self._err('Expected <%s> to not be in %s, but was.' % (self.val, self._fmt_items(items)))
        return self

### numeric assertions ###

    COMPAREABLE_TYPES = set([datetime.datetime, datetime.timedelta, datetime.date, datetime.time])
    NON_COMPAREABLE_TYPES = set([complex])

    def _validate_compareable(self, other):
        self_type = type(self.val)
        other_type = type(other)

        if self_type in self.NON_COMPAREABLE_TYPES:
            raise TypeError('ordering is not defined for type <%s>' % self_type.__name__)
        if self_type in self.COMPAREABLE_TYPES:
            if other_type is not self_type:
                raise TypeError('given arg must be <%s>, but was <%s>' % (self_type.__name__, other_type.__name__))
            return
        if isinstance(self.val, numbers.Number):
            if not isinstance(other, numbers.Number):
                raise TypeError('given arg must be a number, but was <%s>' % other_type.__name__)
            return
        raise TypeError('ordering is not defined for type <%s>' % self_type.__name__)

    def _validate_number(self):
        """Raise TypeError if val is not numeric."""
        if isinstance(self.val, numbers.Number) is False:
            raise TypeError('val is not numeric')

    def _validate_real(self):
        """Raise TypeError if val is not real number."""
        if isinstance(self.val, numbers.Real) is False:
            raise TypeError('val is not real number')

    def is_zero(self):
        """Asserts that val is numeric and equal to zero."""
        self._validate_number()
        return self.is_equal_to(0)

    def is_not_zero(self):
        """Asserts that val is numeric and not equal to zero."""
        self._validate_number()
        return self.is_not_equal_to(0)

    def is_nan(self):
        """Asserts that val is real number and NaN (not a number)."""
        self._validate_number()
        self._validate_real()
        if not math.isnan(self.val):
            self._err('Expected <%s> to be <NaN>, but was not.' % self.val)
        return self

    def is_not_nan(self):
        """Asserts that val is real number and not NaN (not a number)."""
        self._validate_number()
        self._validate_real()
        if math.isnan(self.val):
            self._err('Expected not <NaN>, but was.')
        return self

    def is_inf(self):
        """Asserts that val is real number and Inf (infinity)."""
        self._validate_number()
        self._validate_real()
        if not math.isinf(self.val):
            self._err('Expected <%s> to be <Inf>, but was not.' % self.val)
        return self

    def is_not_inf(self):
        """Asserts that val is real number and not Inf (infinity)."""
        self._validate_number()
        self._validate_real()
        if math.isinf(self.val):
            self._err('Expected not <Inf>, but was.')
        return self

    def is_greater_than(self, other):
        """Asserts that val is numeric and is greater than other."""
        self._validate_compareable(other)
        if self.val <= other:
            if type(self.val) is datetime.datetime:
                self._err('Expected <%s> to be greater than <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                self._err('Expected <%s> to be greater than <%s>, but was not.' % (self.val, other))
        return self

    def is_greater_than_or_equal_to(self, other):
        """Asserts that val is numeric and is greater than or equal to other."""
        self._validate_compareable(other)
        if self.val < other:
            if type(self.val) is datetime.datetime:
                self._err('Expected <%s> to be greater than or equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                self._err('Expected <%s> to be greater than or equal to <%s>, but was not.' % (self.val, other))
        return self

    def is_less_than(self, other):
        """Asserts that val is numeric and is less than other."""
        self._validate_compareable(other)
        if self.val >= other:
            if type(self.val) is datetime.datetime:
                self._err('Expected <%s> to be less than <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                self._err('Expected <%s> to be less than <%s>, but was not.' % (self.val, other))
        return self

    def is_less_than_or_equal_to(self, other):
        """Asserts that val is numeric and is less than or equal to other."""
        self._validate_compareable(other)
        if self.val > other:
            if type(self.val) is datetime.datetime:
                self._err('Expected <%s> to be less than or equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                self._err('Expected <%s> to be less than or equal to <%s>, but was not.' % (self.val, other))
        return self

    def is_positive(self):
        """Asserts that val is numeric and greater than zero."""
        return self.is_greater_than(0)

    def is_negative(self):
        """Asserts that val is numeric and less than zero."""
        return self.is_less_than(0)

    def is_between(self, low, high):
        """Asserts that val is numeric and is between low and high."""
        val_type = type(self.val)
        self._validate_between_args(val_type, low, high)

        if self.val < low or self.val > high:
            if val_type is datetime.datetime:
                self._err('Expected <%s> to be between <%s> and <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), low.strftime('%Y-%m-%d %H:%M:%S'), high.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                self._err('Expected <%s> to be between <%s> and <%s>, but was not.' % (self.val, low, high))
        return self

    def is_not_between(self, low, high):
        """Asserts that val is numeric and is between low and high."""
        val_type = type(self.val)
        self._validate_between_args(val_type, low, high)

        if self.val >= low and self.val <= high:
            if val_type is datetime.datetime:
                self._err('Expected <%s> to not be between <%s> and <%s>, but was.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), low.strftime('%Y-%m-%d %H:%M:%S'), high.strftime('%Y-%m-%d %H:%M:%S')))
            else:
                self._err('Expected <%s> to not be between <%s> and <%s>, but was.' % (self.val, low, high))
        return self

    def is_close_to(self, other, tolerance):
        """Asserts that val is numeric and is close to other within tolerance."""
        self._validate_close_to_args(self.val, other, tolerance)

        if self.val < (other-tolerance) or self.val > (other+tolerance):
            if type(self.val) is datetime.datetime:
                tolerance_seconds = tolerance.days * 86400 + tolerance.seconds + tolerance.microseconds / 1000000
                h, rem = divmod(tolerance_seconds, 3600)
                m, s = divmod(rem, 60)
                self._err('Expected <%s> to be close to <%s> within tolerance <%d:%02d:%02d>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S'), h, m, s))
            else:
                self._err('Expected <%s> to be close to <%s> within tolerance <%s>, but was not.' % (self.val, other, tolerance))
        return self

    def is_not_close_to(self, other, tolerance):
        """Asserts that val is numeric and is not close to other within tolerance."""
        self._validate_close_to_args(self.val, other, tolerance)

        if self.val >= (other-tolerance) and self.val <= (other+tolerance):
            if type(self.val) is datetime.datetime:
                tolerance_seconds = tolerance.days * 86400 + tolerance.seconds + tolerance.microseconds / 1000000
                h, rem = divmod(tolerance_seconds, 3600)
                m, s = divmod(rem, 60)
                self._err('Expected <%s> to not be close to <%s> within tolerance <%d:%02d:%02d>, but was.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S'), h, m, s))
            else:
                self._err('Expected <%s> to not be close to <%s> within tolerance <%s>, but was.' % (self.val, other, tolerance))
        return self

### string assertions ###
    def is_equal_to_ignoring_case(self, other):
        """Asserts that val is case-insensitive equal to other."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a string')
        if not isinstance(other, str_types):
            raise TypeError('given arg must be a string')
        if self.val.lower() != other.lower():
            self._err('Expected <%s> to be case-insensitive equal to <%s>, but was not.' % (self.val, other))
        return self

    def contains_ignoring_case(self, *items):
        """Asserts that val is string and contains the given item or items."""
        if len(items) == 0:
            raise ValueError('one or more args must be given')
        if isinstance(self.val, str_types):
            if len(items) == 1:
                if not isinstance(items[0], str_types):
                    raise TypeError('given arg must be a string')
                if items[0].lower() not in self.val.lower():
                    self._err('Expected <%s> to case-insensitive contain item <%s>, but did not.' % (self.val, items[0]))
            else:
                missing = []
                for i in items:
                    if not isinstance(i, str_types):
                        raise TypeError('given args must all be strings')
                    if i.lower() not in self.val.lower():
                        missing.append(i)
                if missing:
                    self._err('Expected <%s> to case-insensitive contain items %s, but did not contain %s.' % (self.val, self._fmt_items(items), self._fmt_items(missing)))
        elif isinstance(self.val, collections.Iterable):
            missing = []
            for i in items:
                if not isinstance(i, str_types):
                    raise TypeError('given args must all be strings')
                found = False
                for v in self.val:
                    if not isinstance(v, str_types):
                        raise TypeError('val items must all be strings')
                    if i.lower() == v.lower():
                        found = True
                        break
                if not found:
                    missing.append(i)
            if missing:
                self._err('Expected <%s> to case-insensitive contain items %s, but did not contain %s.' % (self.val, self._fmt_items(items), self._fmt_items(missing)))
        else:
            raise TypeError('val is not a string or iterable')
        return self

    def starts_with(self, prefix):
        """Asserts that val is string or iterable and starts with prefix."""
        if prefix is None:
            raise TypeError('given prefix arg must not be none')
        if isinstance(self.val, str_types):
            if not isinstance(prefix, str_types):
                raise TypeError('given prefix arg must be a string')
            if len(prefix) == 0:
                raise ValueError('given prefix arg must not be empty')
            if not self.val.startswith(prefix):
                self._err('Expected <%s> to start with <%s>, but did not.' % (self.val, prefix))
        elif isinstance(self.val, collections.Iterable):
            if len(self.val) == 0:
                raise ValueError('val must not be empty')
            first = next(iter(self.val))
            if first != prefix:
                self._err('Expected %s to start with <%s>, but did not.' % (self.val, prefix))
        else:
            raise TypeError('val is not a string or iterable')
        return self

    def ends_with(self, suffix):
        """Asserts that val is string or iterable and ends with suffix."""
        if suffix is None:
            raise TypeError('given suffix arg must not be none')
        if isinstance(self.val, str_types):
            if not isinstance(suffix, str_types):
                raise TypeError('given suffix arg must be a string')
            if len(suffix) == 0:
                raise ValueError('given suffix arg must not be empty')
            if not self.val.endswith(suffix):
                self._err('Expected <%s> to end with <%s>, but did not.' % (self.val, suffix))
        elif isinstance(self.val, collections.Iterable):
            if len(self.val) == 0:
                raise ValueError('val must not be empty')
            last = None
            for last in self.val:
                pass
            if last != suffix:
                self._err('Expected %s to end with <%s>, but did not.' % (self.val, suffix))
        else:
            raise TypeError('val is not a string or iterable')
        return self

    def matches(self, pattern):
        """Asserts that val is string and matches regex pattern."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a string')
        if not isinstance(pattern, str_types):
            raise TypeError('given pattern arg must be a string')
        if len(pattern) == 0:
            raise ValueError('given pattern arg must not be empty')
        if re.search(pattern, self.val) is None:
            self._err('Expected <%s> to match pattern <%s>, but did not.' % (self.val, pattern))
        return self

    def does_not_match(self, pattern):
        """Asserts that val is string and does not match regex pattern."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a string')
        if not isinstance(pattern, str_types):
            raise TypeError('given pattern arg must be a string')
        if len(pattern) == 0:
            raise ValueError('given pattern arg must not be empty')
        if re.search(pattern, self.val) is not None:
            self._err('Expected <%s> to not match pattern <%s>, but did.' % (self.val, pattern))
        return self

    def is_alpha(self):
        """Asserts that val is non-empty string and all characters are alphabetic."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a string')
        if len(self.val) == 0:
            raise ValueError('val is empty')
        if not self.val.isalpha():
            self._err('Expected <%s> to contain only alphabetic chars, but did not.' % self.val)
        return self

    def is_digit(self):
        """Asserts that val is non-empty string and all characters are digits."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a string')
        if len(self.val) == 0:
            raise ValueError('val is empty')
        if not self.val.isdigit():
            self._err('Expected <%s> to contain only digits, but did not.' % self.val)
        return self

    def is_lower(self):
        """Asserts that val is non-empty string and all characters are lowercase."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a string')
        if len(self.val) == 0:
            raise ValueError('val is empty')
        if self.val != self.val.lower():
            self._err('Expected <%s> to contain only lowercase chars, but did not.' % self.val)
        return self

    def is_upper(self):
        """Asserts that val is non-empty string and all characters are uppercase."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a string')
        if len(self.val) == 0:
            raise ValueError('val is empty')
        if self.val != self.val.upper():
            self._err('Expected <%s> to contain only uppercase chars, but did not.' % self.val)
        return self

    def is_unicode(self):
        """Asserts that val is a unicode string."""
        if type(self.val) is not unicode:
            self._err('Expected <%s> to be unicode, but was <%s>.' % (self.val, type(self.val).__name__))
        return self

### collection assertions ###
    def is_iterable(self):
        """Asserts that val is iterable collection."""
        if not isinstance(self.val, collections.Iterable):
            self._err('Expected iterable, but was not.')
        return self

    def is_not_iterable(self):
        """Asserts that val is not iterable collection."""
        if isinstance(self.val, collections.Iterable):
            self._err('Expected not iterable, but was.')
        return self

    def is_subset_of(self, *supersets):
        """Asserts that val is iterable and a subset of the given superset or flattened superset if multiple supersets are given."""
        if not isinstance(self.val, collections.Iterable):
            raise TypeError('val is not iterable')
        if len(supersets) == 0:
            raise ValueError('one or more superset args must be given')

        missing = []
        if hasattr(self.val, 'keys') and callable(getattr(self.val, 'keys')) and hasattr(self.val, '__getitem__'):
            # flatten superset dicts
            superdict = {}
            for l,j in enumerate(supersets):
                self._check_dict_like(j, check_values=False, name='arg #%d' % (l+1))
                for k in j.keys():
                    superdict.update({k: j[k]})

            for i in self.val.keys():
                if i not in superdict:
                    missing.append({i: self.val[i]}) # bad key
                elif self.val[i] != superdict[i]:
                    missing.append({i: self.val[i]}) # bad val
            if missing:
                self._err('Expected <%s> to be subset of %s, but %s %s missing.' % (self.val, self._fmt_items(superdict), self._fmt_items(missing), 'was' if len(missing) == 1 else 'were'))
        else:
            # flatten supersets
            superset = set()
            for j in supersets:
                try:
                    for k in j:
                        superset.add(k)
                except Exception:
                    superset.add(j)

            for i in self.val:
                if i not in superset:
                    missing.append(i)
            if missing:
                self._err('Expected <%s> to be subset of %s, but %s %s missing.' % (self.val, self._fmt_items(superset), self._fmt_items(missing), 'was' if len(missing) == 1 else 'were'))

        return self

### dict assertions ###
    def contains_key(self, *keys):
        """Asserts the val is a dict and contains the given key or keys.  Alias for contains()."""
        self._check_dict_like(self.val, check_values=False, check_getitem=False)
        return self.contains(*keys)

    def does_not_contain_key(self, *keys):
        """Asserts the val is a dict and does not contain the given key or keys.  Alias for does_not_contain()."""
        self._check_dict_like(self.val, check_values=False, check_getitem=False)
        return self.does_not_contain(*keys)

    def contains_value(self, *values):
        """Asserts that val is a dict and contains the given value or values."""
        self._check_dict_like(self.val, check_getitem=False)
        if len(values) == 0:
            raise ValueError('one or more value args must be given')
        missing = []
        for v in values:
            if v not in self.val.values():
                missing.append(v)
        if missing:
            self._err('Expected <%s> to contain values %s, but did not contain %s.' % (self.val, self._fmt_items(values), self._fmt_items(missing)))
        return self

    def does_not_contain_value(self, *values):
        """Asserts that val is a dict and does not contain the given value or values."""
        self._check_dict_like(self.val, check_getitem=False)
        if len(values) == 0:
            raise ValueError('one or more value args must be given')
        else:
            found = []
            for v in values:
                if v in self.val.values():
                    found.append(v)
            if found:
                self._err('Expected <%s> to not contain values %s, but did contain %s.' % (self.val, self._fmt_items(values), self._fmt_items(found)))
        return self

    def contains_entry(self, *entries):
        """Asserts that val is a dict and contains the given entry or entries."""
        self._check_dict_like(self.val, check_values=False)
        if len(entries) == 0:
            raise ValueError('one or more entry args must be given')
        missing = []
        for e in entries:
            if type(e) is not dict:
                raise TypeError('given entry arg must be a dict')
            if len(e) != 1:
                raise ValueError('given entry args must contain exactly one key-value pair')
            k = next(iter(e))
            if k not in self.val:
                missing.append(e) # bad key
            elif self.val[k] != e[k]:
                missing.append(e) # bad val
        if missing:
            self._err('Expected <%s> to contain entries %s, but did not contain %s.' % (self.val, self._fmt_items(entries), self._fmt_items(missing)))
        return self

    def does_not_contain_entry(self, *entries):
        """Asserts that val is a dict and does not contain the given entry or entries."""
        self._check_dict_like(self.val, check_values=False)
        if len(entries) == 0:
            raise ValueError('one or more entry args must be given')
        found = []
        for e in entries:
            if type(e) is not dict:
                raise TypeError('given entry arg must be a dict')
            if len(e) != 1:
                raise ValueError('given entry args must contain exactly one key-value pair')
            k = next(iter(e))
            if k in self.val and e[k] == self.val[k]:
                found.append(e)
        if found:
            self._err('Expected <%s> to not contain entries %s, but did contain %s.' % (self.val, self._fmt_items(entries), self._fmt_items(found)))
        return self

### datetime assertions ###
    def is_before(self, other):
        """Asserts that val is a date and is before other date."""
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val >= other:
            self._err('Expected <%s> to be before <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
        return self

    def is_after(self, other):
        """Asserts that val is a date and is after other date."""
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val <= other:
            self._err('Expected <%s> to be after <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
        return self

    def is_equal_to_ignoring_milliseconds(self, other):
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val.date() != other.date() or self.val.hour != other.hour or self.val.minute != other.minute or self.val.second != other.second:
            self._err('Expected <%s> to be equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M:%S'), other.strftime('%Y-%m-%d %H:%M:%S')))
        return self

    def is_equal_to_ignoring_seconds(self, other):
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val.date() != other.date() or self.val.hour != other.hour or self.val.minute != other.minute:
            self._err('Expected <%s> to be equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d %H:%M'), other.strftime('%Y-%m-%d %H:%M')))
        return self

    def is_equal_to_ignoring_time(self, other):
        if type(self.val) is not datetime.datetime:
            raise TypeError('val must be datetime, but was type <%s>' % type(self.val).__name__)
        if type(other) is not datetime.datetime:
            raise TypeError('given arg must be datetime, but was type <%s>' % type(other).__name__)
        if self.val.date() != other.date():
            self._err('Expected <%s> to be equal to <%s>, but was not.' % (self.val.strftime('%Y-%m-%d'), other.strftime('%Y-%m-%d')))
        return self

### file assertions ###
    def exists(self):
        """Asserts that val is a path and that it exists."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a path')
        if not os.path.exists(self.val):
            self._err('Expected <%s> to exist, but was not found.' % self.val)
        return self

    def does_not_exist(self):
        """Asserts that val is a path and that it does not exist."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a path')
        if os.path.exists(self.val):
            self._err('Expected <%s> to not exist, but was found.' % self.val)
        return self

    def is_file(self):
        """Asserts that val is an existing path to a file."""
        self.exists()
        if not os.path.isfile(self.val):
            self._err('Expected <%s> to be a file, but was not.' % self.val)
        return self

    def is_directory(self):
        """Asserts that val is an existing path to a directory."""
        self.exists()
        if not os.path.isdir(self.val):
            self._err('Expected <%s> to be a directory, but was not.' % self.val)
        return self

    def is_named(self, filename):
        """Asserts that val is an existing path to a file and that file is named filename."""
        self.is_file()
        if not isinstance(filename, str_types):
            raise TypeError('given filename arg must be a path')
        val_filename = os.path.basename(os.path.abspath(self.val))
        if val_filename != filename:
            self._err('Expected filename <%s> to be equal to <%s>, but was not.' % (val_filename, filename))
        return self

    def is_child_of(self, parent):
        """Asserts that val is an existing path to a file and that file is a child of parent."""
        self.is_file()
        if not isinstance(parent, str_types):
            raise TypeError('given parent directory arg must be a path')
        val_abspath = os.path.abspath(self.val)
        parent_abspath = os.path.abspath(parent)
        if not val_abspath.startswith(parent_abspath):
            self._err('Expected file <%s> to be a child of <%s>, but was not.' % (val_abspath, parent_abspath))
        return self

### collection of objects assertions ###
    def extracting(self, *names, **kwargs):
        """Asserts that val is collection, then extracts the named properties or named zero-arg methods into a list (or list of tuples if multiple names are given)."""
        if not isinstance(self.val, collections.Iterable):
            raise TypeError('val is not iterable')
        if isinstance(self.val, str_types):
            raise TypeError('val must not be string')
        if len(names) == 0:
            raise ValueError('one or more name args must be given')

        def _extract(x, name):
            if self._check_dict_like(x, check_values=False, return_as_bool=True):
                if name in x:
                    return x[name]
                else:
                    raise ValueError('item keys %s did not contain key <%s>' % (list(x.keys()), name))
            elif hasattr(x, name):
                attr = getattr(x, name)
                if callable(attr):
                    try:
                        return attr()
                    except TypeError:
                        raise ValueError('val method <%s()> exists, but is not zero-arg method' % name)
                else:
                    return attr
            else:
                raise ValueError('val does not have property or zero-arg method <%s>' % name)

        def _filter(x):
            if 'filter' in kwargs:
                if isinstance(kwargs['filter'], str_types):
                    return bool(_extract(x, kwargs['filter']))
                elif self._check_dict_like(kwargs['filter'], check_values=False, return_as_bool=True):
                    for k in kwargs['filter']:
                        if isinstance(k, str_types):
                            if _extract(x, k) != kwargs['filter'][k]:
                                return False
                    return True
                elif callable(kwargs['filter']):
                    return kwargs['filter'](x)
                return False
            return True

        def _sort(x):
            if 'sort' in kwargs:
                if isinstance(kwargs['sort'], str_types):
                    return _extract(x, kwargs['sort'])
                elif isinstance(kwargs['sort'], collections.Iterable):
                    items = []
                    for k in kwargs['sort']:
                        if isinstance(k, str_types):
                            items.append(_extract(x, k))
                    return tuple(items)
                elif callable(kwargs['sort']):
                    return kwargs['sort'](x)
            return 0

        extracted = []
        for i in sorted(self.val, key=lambda x: _sort(x)):
            if _filter(i):
                items = [_extract(i, name) for name in names]
                extracted.append(tuple(items) if len(items) > 1 else items[0])
        return AssertionBuilder(extracted, self.description, self.kind)

### dynamic assertions ###
    def __getattr__(self, attr):
        """Asserts that val has attribute attr and that attribute's value is equal to other via a dynamic assertion of the form: has_<attr>()."""
        if not attr.startswith('has_'):
            raise AttributeError('assertpy has no assertion <%s()>' % attr)

        attr_name = attr[4:]
        err_msg = False
        is_dict = isinstance(self.val, collections.Iterable) and hasattr(self.val, '__getitem__')

        if not hasattr(self.val, attr_name):
            if is_dict:
                if attr_name not in self.val:
                    err_msg = 'Expected key <%s>, but val has no key <%s>.' % (attr_name, attr_name)
            else:
                err_msg = 'Expected attribute <%s>, but val has no attribute <%s>.' % (attr_name, attr_name)

        def _wrapper(*args, **kwargs):
            if err_msg:
                self._err(err_msg) # ok to raise AssertionError now that we are inside wrapper
            else:
                if len(args) != 1:
                    raise TypeError('assertion <%s()> takes exactly 1 argument (%d given)' % (attr, len(args)))

                try:
                    val_attr = getattr(self.val, attr_name)
                except AttributeError:
                    val_attr = self.val[attr_name]

                if callable(val_attr):
                    try:
                        actual = val_attr()
                    except TypeError:
                        raise TypeError('val does not have zero-arg method <%s()>' % attr_name)
                else:
                    actual = val_attr

                expected = args[0]
                if actual != expected:
                    self._err('Expected <%s> to be equal to <%s> on %s <%s>, but was not.' % (actual, expected, 'key' if is_dict else 'attribute', attr_name))
            return self

        return _wrapper

### expected exceptions ###
    def raises(self, ex):
        """Asserts that val is callable and that when called raises the given error."""
        if not callable(self.val):
            raise TypeError('val must be callable')
        if not issubclass(ex, BaseException):
            raise TypeError('given arg must be exception')
        return AssertionBuilder(self.val, self.description, self.kind, ex)

    def when_called_with(self, *some_args, **some_kwargs):
        """Asserts the val callable when invoked with the given args and kwargs raises the expected exception."""
        if not self.expected:
            raise TypeError('expected exception not set, raises() must be called first')
        try:
            self.val(*some_args, **some_kwargs)
        except BaseException as e:
            if issubclass(type(e), self.expected):
                # chain on with exception message as val
                return AssertionBuilder(str(e), self.description, self.kind)
            else:
                # got exception, but wrong type, so raise
                self._err('Expected <%s> to raise <%s> when called with (%s), but raised <%s>.' % (
                    self.val.__name__,
                    self.expected.__name__,
                    self._fmt_args_kwargs(*some_args, **some_kwargs),
                    type(e).__name__))

        # didn't fail as expected, so raise
        self._err('Expected <%s> to raise <%s> when called with (%s).' % (
            self.val.__name__,
            self.expected.__name__,
            self._fmt_args_kwargs(*some_args, **some_kwargs)))

### helpers ###
    def _err(self, msg):
        """Helper to raise an AssertionError, and optionally prepend custom description."""
        out = '%s%s' % ('[%s] ' % self.description if len(self.description) > 0 else '', msg)
        if self.kind == 'warn':
            print(out)
            return self
        elif self.kind == 'soft':
            global _soft_err
            _soft_err.append(out)
            return self
        else:
            raise AssertionError(out)

    def _fmt_items(self, i):
        if len(i) == 0:
            return '<>'
        elif len(i) == 1:
            return '<%s>' % i[0]
        else:
            return '<%s>' % str(i).lstrip('([').rstrip(',])')

    def _fmt_args_kwargs(self, *some_args, **some_kwargs):
        """Helper to convert the given args and kwargs into a string."""
        if some_args:
            out_args = str(some_args).lstrip('(').rstrip(',)')
        if some_kwargs:
            out_kwargs = ', '.join([str(i).lstrip('(').rstrip(')').replace(', ',': ') for i in [
                    (k,some_kwargs[k]) for k in sorted(some_kwargs.keys())]])

        if some_args and some_kwargs:
            return out_args + ', ' + out_kwargs
        elif some_args:
            return out_args
        elif some_kwargs:
            return out_kwargs
        else:
            return ''

    def _validate_between_args(self, val_type, low, high):
        low_type = type(low)
        high_type = type(high)

        if val_type in self.NON_COMPAREABLE_TYPES:
            raise TypeError('ordering is not defined for type <%s>' % val_type.__name__)

        if val_type in self.COMPAREABLE_TYPES:
            if low_type is not val_type:
                raise TypeError('given low arg must be <%s>, but was <%s>' % (val_type.__name__, low_type.__name__))
            if high_type is not val_type:
                raise TypeError('given high arg must be <%s>, but was <%s>' % (val_type.__name__, low_type.__name__))
        elif isinstance(self.val, numbers.Number):
            if isinstance(low, numbers.Number) is False:
                raise TypeError('given low arg must be numeric, but was <%s>' % low_type.__name__)
            if isinstance(high, numbers.Number) is False:
                raise TypeError('given high arg must be numeric, but was <%s>' % high_type.__name__)
        else:
            raise TypeError('ordering is not defined for type <%s>' % val_type.__name__)

        if low > high:
            raise ValueError('given low arg must be less than given high arg')

    def _validate_close_to_args(self, val, other, tolerance):
        if type(val) is complex or type(other) is complex or type(tolerance) is complex:
            raise TypeError('ordering is not defined for complex numbers')

        if isinstance(val, numbers.Number) is False and type(val) is not datetime.datetime:
            raise TypeError('val is not numeric or datetime')

        if type(val) is datetime.datetime:
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

    def _check_dict_like(self, d, check_keys=True, check_values=True, check_getitem=True, name='val', return_as_bool=False):
        if not isinstance(d, collections.Iterable):
            if return_as_bool:
                return False
            else:
                raise TypeError('%s <%s> is not dict-like: not iterable' % (name, type(d).__name__))
        if check_keys:
            if not hasattr(d, 'keys') or not callable(getattr(d, 'keys')):
                if return_as_bool:
                    return False
                else:
                    raise TypeError('%s <%s> is not dict-like: missing keys()' % (name, type(d).__name__))
        if check_values:
            if not hasattr(d, 'values') or not callable(getattr(d, 'values')):
                if return_as_bool:
                    return False
                else:
                    raise TypeError('%s <%s> is not dict-like: missing values()' % (name, type(d).__name__))
        if check_getitem:
            if not hasattr(d, '__getitem__'):
                if return_as_bool:
                    return False
                else:
                    raise TypeError('%s <%s> is not dict-like: missing [] accessor' % (name, type(d).__name__))
        if return_as_bool:
            return True

    def _dict_not_equal(self, val, other, ignore=None, include=None):
        if ignore or include:
            ignores = self._dict_ignore(ignore)
            includes = self._dict_include(include)

            # guarantee include keys are in val
            if include:
                missing = []
                for i in includes:
                    if i not in val:
                        missing.append(i)
                if missing:
                    self._err('Expected <%s> to include key%s %s, but did not include key%s %s.' % (
                        val,
                        '' if len(includes) == 1 else 's',
                        self._fmt_items(['.'.join([str(s) for s in i]) if type(i) is tuple else i for i in includes]),
                        '' if len(missing) == 1 else 's',
                        self._fmt_items(missing)))

            if ignore and include:
                k1 = set([k for k in val if k not in ignores and k in includes])
            elif ignore:
                k1 = set([k for k in val if k not in ignores])
            else: # include
                k1 = set([k for k in val if k in includes])

            if ignore and include:
                k2 = set([k for k in other if k not in ignores and k in includes])
            elif ignore:
                k2 = set([k for k in other if k not in ignores])
            else: # include
                k2 = set([k for k in other if k in includes])

            if k1 != k2:
                return True
            else:
                for k in k1:
                    if self._check_dict_like(val[k], check_values=False, return_as_bool=True) and self._check_dict_like(other[k], check_values=False, return_as_bool=True):
                        return self._dict_not_equal(val[k], other[k],
                            ignore=[i[1:] for i in ignores if type(i) is tuple and i[0] == k] if ignore else None,
                            include=[i[1:] for i in self._dict_ignore(include) if type(i) is tuple and i[0] == k] if include else None)
                    elif val[k] != other[k]:
                        return True
            return False
        else:
            return val != other

    def _dict_ignore(self, ignore):
        return [i[0] if type(i) is tuple and len(i) == 1 else i \
            for i in (ignore if type(ignore) is list else [ignore])]

    def _dict_include(self, include):
        return [i[0] if type(i) is tuple else i \
            for i in (include if type(include) is list else [include])]

    def _dict_err(self, val, other, ignore=None, include=None):
        def _dict_repr(d, other):
            out = ''
            ellip = False
            for k,v in d.items():
                if k not in other:
                    out += '%s%s: %s' % (', ' if len(out) > 0 else '', repr(k), repr(v))
                elif v != other[k]:
                    out += '%s%s: %s' % (', ' if len(out) > 0 else '', repr(k),
                        _dict_repr(v, other[k]) if self._check_dict_like(v, check_values=False, return_as_bool=True) and self._check_dict_like(other[k], check_values=False, return_as_bool=True) else repr(v)
                    )
                else:
                    ellip = True
            return '{%s%s}' % ('..' if ellip and len(out) == 0 else '.., ' if ellip else '', out)

        if ignore:
            ignores = self._dict_ignore(ignore)
            ignore_err = ' ignoring keys %s' % self._fmt_items(['.'.join([str(s) for s in i]) if type(i) is tuple else i for i in ignores])
        if include:
            includes = self._dict_ignore(include)
            include_err = ' including keys %s' % self._fmt_items(['.'.join([str(s) for s in i]) if type(i) is tuple else i for i in includes])

        self._err('Expected <%s> to be equal to <%s>%s%s, but was not.' % (
            _dict_repr(val, other),
            _dict_repr(other, val),
            ignore_err if ignore else '',
            include_err if include else ''
        ))

### snapshot testing ###
    def snapshot(self, id=None, path='__snapshots'):
        if sys.version_info[0] < 3:
            raise NotImplementedError('snapshot testing requires Python 3')

        class _Encoder(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, set):
                    return {'__type__': 'set', '__data__': list(o)}
                elif isinstance(o, complex):
                    return {'__type__': 'complex', '__data__': [o.real, o.imag]}
                elif isinstance(o, datetime.datetime):
                    return {'__type__': 'datetime', '__data__': o.strftime('%Y-%m-%d %H:%M:%S')}
                elif '__dict__' in dir(o) and type(o) is not type:
                    return {
                        '__type__': 'instance',
                        '__class__': o.__class__.__name__,
                        '__module__': o.__class__.__module__,
                        '__data__': o.__dict__
                    }
                return json.JSONEncoder.default(self, o)

        class _Decoder(json.JSONDecoder):
            def __init__(self):
                json.JSONDecoder.__init__(self, object_hook=self.object_hook)

            def object_hook(self, d):
                if '__type__' in d and '__data__' in d:
                    if d['__type__'] == 'set':
                        return set(d['__data__'])
                    elif d['__type__'] == 'complex':
                        return complex(d['__data__'][0], d['__data__'][1])
                    elif d['__type__'] == 'datetime':
                        return datetime.datetime.strptime(d['__data__'], '%Y-%m-%d %H:%M:%S')
                    elif d['__type__'] == 'instance':
                        mod = __import__(d['__module__'], fromlist=[d['__class__']])
                        klass = getattr(mod, d['__class__'])
                        inst = klass.__new__(klass)
                        inst.__dict__ = d['__data__']
                        return inst
                return d

        def _save(name, val):
            with open(name, 'w') as fp:
                json.dump(val, fp, indent=2, separators=(',', ': '), sort_keys=True, cls=_Encoder)

        def _load(name):
            with open(name, 'r') as fp:
                return json.load(fp, cls=_Decoder)

        def _name(path, name):
            try:
                return os.path.join(path, 'snap-%s.json' % name.replace(' ','_').lower())
            except Exception:
                raise ValueError('failed to create snapshot filename, either bad path or bad name')

        if id:
            # custom id
            snapname = _name(path, id)
        else:
            # make id from filename and line number
            f = inspect.currentframe()
            fpath = os.path.basename(f.f_back.f_code.co_filename)
            fname = os.path.splitext(fpath)[0]
            lineno = str(f.f_back.f_lineno)
            snapname = _name(path, fname)

        if not os.path.exists(path):
            os.makedirs(path)

        if os.path.isfile(snapname):
            # snap exists, so load
            snap = _load(snapname)

            if id:
                # custom id, so test
                return self.is_equal_to(snap)
            else:
                if lineno in snap:
                    # found sub-snap, so test
                    return self.is_equal_to(snap[lineno])
                else:
                    # lineno not in snap, so create sub-snap and pass
                    snap[lineno] = self.val
                    _save(snapname, snap)
        else:
            # no snap, so create and pass
            _save(snapname, self.val if id else {lineno: self.val})

        return self
