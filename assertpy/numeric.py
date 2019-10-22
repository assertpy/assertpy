# Copyright (c) 2015-2019, Activision Publishing, Inc.
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

from __future__ import division
import sys
import math
import numbers
import datetime


class NumericMixin(object):
    """Numeric assertions mixin."""

    NUMERIC_COMPAREABLE = set([datetime.datetime, datetime.timedelta, datetime.date, datetime.time])
    NUMERIC_NON_COMPAREABLE = set([complex])

    def _validate_compareable(self, other):
        self_type = type(self.val)
        other_type = type(other)

        if self_type in self.NUMERIC_NON_COMPAREABLE:
            raise TypeError('ordering is not defined for type <%s>' % self_type.__name__)
        if self_type in self.NUMERIC_COMPAREABLE:
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
