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


class BaseMixin(object):
    """Base mixin."""

    def described_as(self, description):
        """Describes the assertion.  On failure, the description is included in the error message."""
        self.description = str(description)
        return self

    def is_equal_to(self, other, **kwargs):
        """Asserts that val is equal to other."""
        if self._check_dict_like(self.val, check_values=False, return_as_bool=True) and \
                self._check_dict_like(other, check_values=False, return_as_bool=True):
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

    def _type(self, val):
        if hasattr(val, '__name__'):
            return val.__name__
        elif hasattr(val, '__class__'):
            return val.__class__.__name__
        return 'unknown'

    def is_type_of(self, some_type):
        """Asserts that val is of the given type."""
        if type(some_type) is not type and not issubclass(type(some_type), type):
            raise TypeError('given arg must be a type')
        if type(self.val) is not some_type:
            t = self._type(self.val)
            self._err('Expected <%s:%s> to be of type <%s>, but was not.' % (self.val, t, some_type.__name__))
        return self

    def is_instance_of(self, some_class):
        """Asserts that val is an instance of the given class."""
        try:
            if not isinstance(self.val, some_class):
                t = self._type(self.val)
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
