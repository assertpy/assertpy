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

from assertpy import assert_that

class TestNumbers(object):

    def test_is_greater_than(self):
        assert_that(123).is_greater_than(100)
        assert_that(123).is_greater_than(0)
        assert_that(123).is_greater_than(-100)
        assert_that(123).is_greater_than(122.5)

    def test_is_greater_than_failure(self):
        try:
            assert_that(123).is_greater_than(1000)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be greater than <1000>, but was not.')
            return
        self.fail('should not fail')

    def test_is_greater_than_complex_failure(self):
        try:
            assert_that(1 + 2j).is_greater_than(0)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('ordering is not defined for complex numbers')
            return
        self.fail('should not fail')

    def test_is_greater_than_bad_value_type_failure(self):
        try:
            assert_that('foo').is_greater_than(0)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not numeric')
            return
        self.fail('should not fail')

    def test_is_greater_than_bad_arg_type_failure(self):
        try:
            assert_that(123).is_greater_than('foo')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be numeric')
            return
        self.fail('should not fail')

    def test_is_less_than(self):
        assert_that(123).is_less_than(1000)
        assert_that(123).is_less_than(1e6)
        assert_that(-123).is_less_than(-100)
        assert_that(123).is_less_than(123.001)

    def test_is_less_than_failure(self):
        try:
            assert_that(123).is_less_than(1)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be less than <1>, but was not.')
            return
        self.fail('should not fail')

    def test_is_less_than_complex_failure(self):
        try:
            assert_that(1 + 2j).is_less_than(0)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('ordering is not defined for complex numbers')
            return
        self.fail('should not fail')

    def test_is_less_than_bad_value_type_failure(self):
        try:
            assert_that('foo').is_less_than(0)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not numeric')
            return
        self.fail('should not fail')

    def test_is_less_than_bad_arg_type_failure(self):
        try:
            assert_that(123).is_less_than('foo')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be numeric')
            return
        self.fail('should not fail')

    def test_is_between(self):
        assert_that(123).is_between(120,125)
        assert_that(123).is_between(0,1e6)
        assert_that(-123).is_between(-150,-100)
        assert_that(123).is_between(122.999,123.001)

    def test_is_between_failure(self):
        try:
            assert_that(123).is_between(0,1)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be between <0> and <1>, but was not.')
            return
        self.fail('should not fail')

    def test_is_between_complex_failure(self):
        try:
            assert_that(1 + 2j).is_between(0,1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('ordering is not defined for complex numbers')
            return
        self.fail('should not fail')

    def test_is_between_bad_value_type_failure(self):
        try:
            assert_that('foo').is_between(0,1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not numeric')
            return
        self.fail('should not fail')

    def test_is_between_low_arg_type_failure(self):
        try:
            assert_that(123).is_between('foo',1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given low arg must be numeric')
            return
        self.fail('should not fail')

    def test_is_between_high_arg_type_failure(self):
        try:
            assert_that(123).is_between(0,'foo')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given high arg must be numeric')
            return
        self.fail('should not fail')

    def test_is_between_bad_arg_delta_failure(self):
        try:
            assert_that(123).is_between(1,0)
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given low arg must be less than given high arg')
            return
        self.fail('should not fail')

    def test_is_close_to(self):
        assert_that(123.01).is_close_to(123,1)
        assert_that(0.01).is_close_to(0,1)
        assert_that(-123.01).is_close_to(-123,1)

    def test_is_close_to_failure(self):
        try:
            assert_that(123.01).is_close_to(100,1)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123.01> to be close to <100> within tolerance <1>, but was not.')
            return
        self.fail('should not fail')

    def test_is_close_to_complex_failure(self):
        try:
            assert_that(1 + 2j).is_close_to(0,1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('ordering is not defined for complex numbers')
            return
        self.fail('should not fail')

    def test_is_close_to_bad_value_type_failure(self):
        try:
            assert_that('foo').is_close_to(123,1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not numeric')
            return
        self.fail('should not fail')

    def test_is_close_to_bad_arg_type_failure(self):
        try:
            assert_that(123.01).is_close_to('foo',1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be numeric')
            return
        self.fail('should not fail')

    def test_is_close_to_bad_tolerance_arg_type_failure(self):
        try:
            assert_that(123.01).is_close_to(0,'foo')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given tolerance arg must be numeric')
            return
        self.fail('should not fail')

    def test_is_close_to_negative_tolerance_failure(self):
        try:
            assert_that(123.01).is_close_to(123,-1)
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given tolerance arg must be positive')
            return
        self.fail('should not fail')

    def test_chaining(self):
        assert_that(123).is_greater_than(100).is_less_than(1000).is_between(120,125).is_close_to(100,25)

