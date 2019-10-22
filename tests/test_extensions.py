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

from assertpy import assert_that, add_extension
import numbers


def is_even(self):
    if isinstance(self.val, numbers.Integral) is False:
        raise TypeError('val must be an integer')
    if self.val % 2 != 0:
        self._err('Expected <%s> to be even, but was not.' % (self.val))
    return self

def is_multiple_of(self, other):
    if isinstance(self.val, numbers.Integral) is False:
        raise TypeError('val must be an integer')
    if isinstance(other, numbers.Integral) is False:
        raise TypeError('given arg must be an integer')
    _, rem = divmod(self.val, other)
    if rem != 0:
        self._err('Expected <%s> to be multiple of <%s>, but was not.' % (self.val, other))
    return self



def test_is_even_extension():
    add_extension(is_even)
    assert_that(124).is_even()
    assert_that(124).is_type_of(int).is_even().is_greater_than(123).is_less_than(125).is_equal_to(124)

def test_is_even_extension_failure():
    try:
        add_extension(is_even)
        assert_that(123).is_even()
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to('Expected <123> to be even, but was not.')

def test_is_even_extension_failure_not_callable():
    try:
        add_extension('foo')
        fail('should have raised error')
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to('func must be callable')

def test_is_even_extension_failure_not_integer():
    try:
        add_extension(is_even)
        assert_that(124.0).is_even()
        fail('should have raised error')
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to('val must be an integer')

def test_is_multiple_of_extension():
    add_extension(is_multiple_of)
    assert_that(24).is_multiple_of(1)
    assert_that(24).is_multiple_of(2)
    assert_that(24).is_multiple_of(3)
    assert_that(24).is_multiple_of(4)
    assert_that(24).is_multiple_of(6)
    assert_that(24).is_multiple_of(8)
    assert_that(24).is_multiple_of(12)
    assert_that(24).is_multiple_of(24)
    assert_that(124).is_type_of(int).is_even().is_multiple_of(31).is_equal_to(124)

def test_is_multiple_of_extension_failure():
    try:
        add_extension(is_multiple_of)
        assert_that(24).is_multiple_of(5)
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to('Expected <24> to be multiple of <5>, but was not.')

def test_is_multiple_of_extension_failure_not_integer():
    try:
        add_extension(is_multiple_of)
        assert_that(24.0).is_multiple_of(5)
        fail('should have raised error')
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to('val must be an integer')

def test_is_multiple_of_extension_failure_arg_not_integer():
    try:
        add_extension(is_multiple_of)
        assert_that(24).is_multiple_of('foo')
        fail('should have raised error')
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to('given arg must be an integer')
