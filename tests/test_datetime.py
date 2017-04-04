# Copyright (c) 2015-2017, Activision Publishing, Inc.
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

import datetime
from assertpy import assert_that,fail

class TestDate(object):

    def setup(self):
        self.d1 = datetime.datetime.today()

    def test_is_before(self):
        d2 = datetime.datetime.today()
        assert_that(self.d1).is_before(d2)

    def test_is_before_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(d2).is_before(self.d1)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be before <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')

    def test_is_before_bad_val_type_failure(self):
        try:
            assert_that(123).is_before(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val must be datetime, but was type <int>')

    def test_is_before_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_before(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be datetime, but was type <int>')

    def test_is_after(self):
        d2 = datetime.datetime.today()
        assert_that(d2).is_after(self.d1)

    def test_is_after_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(self.d1).is_after(d2)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be after <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')

    def test_is_after_bad_val_type_failure(self):
        try:
            assert_that(123).is_after(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val must be datetime, but was type <int>')

    def test_is_after_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_after(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be datetime, but was type <int>')

    def test_is_equal_to_ignoring_milliseconds(self):
        assert_that(self.d1).is_equal_to_ignoring_milliseconds(self.d1)

    def test_is_equal_to_ignoring_milliseconds_failure(self):
        try:
            d2 = datetime.datetime.today() + datetime.timedelta(days=1)
            assert_that(self.d1).is_equal_to_ignoring_milliseconds(d2)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be equal to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')

    def test_is_equal_to_ignoring_milliseconds_bad_val_type_failure(self):
        try:
            assert_that(123).is_equal_to_ignoring_milliseconds(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val must be datetime, but was type <int>')

    def test_is_equal_to_ignoring_milliseconds_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_equal_to_ignoring_milliseconds(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be datetime, but was type <int>')

    def test_is_equal_to_ignoring_seconds(self):
        assert_that(self.d1).is_equal_to_ignoring_seconds(self.d1)

    def test_is_equal_to_ignoring_seconds_failure(self):
        try:
            d2 = datetime.datetime.today() + datetime.timedelta(days=1)
            assert_that(self.d1).is_equal_to_ignoring_seconds(d2)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}> to be equal to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}>, but was not.')

    def test_is_equal_to_ignoring_seconds_bad_val_type_failure(self):
        try:
            assert_that(123).is_equal_to_ignoring_seconds(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val must be datetime, but was type <int>')

    def test_is_equal_to_ignoring_seconds_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_equal_to_ignoring_seconds(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be datetime, but was type <int>')

    def test_is_equal_to_ignoring_time(self):
        assert_that(self.d1).is_equal_to_ignoring_time(self.d1)

    def test_is_equal_to_ignoring_time_failure(self):
        try:
            d2 = datetime.datetime.today() + datetime.timedelta(days=1)
            assert_that(self.d1).is_equal_to_ignoring_time(d2)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2}> to be equal to <\d{4}-\d{2}-\d{2}>, but was not.')

    def test_is_equal_to_ignoring_time_bad_val_type_failure(self):
        try:
            assert_that(123).is_equal_to_ignoring_time(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val must be datetime, but was type <int>')

    def test_is_equal_to_ignoring_time_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_equal_to_ignoring_time(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be datetime, but was type <int>')

    def test_is_greater_than(self):
        d2 = datetime.datetime.today()
        assert_that(d2).is_greater_than(self.d1)

    def test_is_greater_than_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(self.d1).is_greater_than(d2)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be greater than <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')

    def test_is_greater_than_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_greater_than(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be <datetime>, but was <int>')

    def test_is_greater_than_or_equal_to(self):
        assert_that(self.d1).is_greater_than_or_equal_to(self.d1)

    def test_is_greater_than_or_equal_to_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(self.d1).is_greater_than_or_equal_to(d2)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be greater than or equal to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')

    def test_is_greater_than_or_equal_to_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_greater_than_or_equal_to(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be <datetime>, but was <int>')

    def test_is_less_than(self):
        d2 = datetime.datetime.today()
        assert_that(self.d1).is_less_than(d2)

    def test_is_less_than_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(d2).is_less_than(self.d1)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be less than <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')

    def test_is_less_than_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_less_than(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be <datetime>, but was <int>')

    def test_is_less_than_or_equal_to(self):
        assert_that(self.d1).is_less_than_or_equal_to(self.d1)

    def test_is_less_than_or_equal_to_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(d2).is_less_than_or_equal_to(self.d1)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be less than or equal to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')

    def test_is_less_than_or_equal_to_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_less_than_or_equal_to(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be <datetime>, but was <int>')

    def test_is_between(self):
        d2 = datetime.datetime.today()
        d3 = datetime.datetime.today()
        assert_that(d2).is_between(self.d1, d3)

    def test_is_between_failure(self):
        try:
            d2 = datetime.datetime.today()
            d3 = datetime.datetime.today()
            assert_that(self.d1).is_between(d2, d3)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be between <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> and <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')

    def test_is_between_bad_arg1_type_failure(self):
        try:
            assert_that(self.d1).is_between(123, 456)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given low arg must be <datetime>, but was <int>')

    def test_is_between_bad_arg2_type_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(self.d1).is_between(d2, 123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given high arg must be <datetime>, but was <datetime>')

    def test_is_close_to(self):
        d2 = datetime.datetime.today()
        assert_that(self.d1).is_close_to(d2, datetime.timedelta(minutes=5))

    def test_is_close_to_failure(self):
        try:
            d2 = self.d1 + datetime.timedelta(minutes=5)
            assert_that(self.d1).is_close_to(d2, datetime.timedelta(minutes=1))
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be close to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> within tolerance <\d+:\d{2}:\d{2}>, but was not.')

    def test_is_close_to_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_close_to(123, 456)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be datetime, but was <int>')

    def test_is_close_to_bad_tolerance_arg_type_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(self.d1).is_close_to(d2, 123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given tolerance arg must be timedelta, but was <int>')

class TestTimedelta(object):

    def setup(self):
        self.t1 = datetime.timedelta(seconds=60)

    def test_is_greater_than(self):
        d2 = datetime.timedelta(seconds=120)
        assert_that(d2).is_greater_than(self.t1)

    def test_is_greater_than_failure(self):
        try:
            t2 = datetime.timedelta(seconds=90)
            assert_that(self.t1).is_greater_than(t2)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{1,2}:\d{2}:\d{2}> to be greater than <\d{1,2}:\d{2}:\d{2}>, but was not.')

    def test_is_greater_than_bad_arg_type_failure(self):
        try:
            assert_that(self.t1).is_greater_than(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be <timedelta>, but was <int>')

    def test_is_greater_than_or_equal_to(self):
        assert_that(self.t1).is_greater_than_or_equal_to(self.t1)

    def test_is_greater_than_or_equal_to_failure(self):
        try:
            t2 = datetime.timedelta(seconds=90)
            assert_that(self.t1).is_greater_than_or_equal_to(t2)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{1,2}:\d{2}:\d{2}> to be greater than or equal to <\d{1,2}:\d{2}:\d{2}>, but was not.')

    def test_is_greater_than_or_equal_to_bad_arg_type_failure(self):
        try:
            assert_that(self.t1).is_greater_than_or_equal_to(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be <timedelta>, but was <int>')

    def test_is_less_than(self):
        t2 = datetime.timedelta(seconds=90)
        assert_that(self.t1).is_less_than(t2)

    def test_is_less_than_failure(self):
        try:
            t2 = datetime.timedelta(seconds=90)
            assert_that(t2).is_less_than(self.t1)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{1,2}:\d{2}:\d{2}> to be less than <\d{1,2}:\d{2}:\d{2}>, but was not.')

    def test_is_less_than_bad_arg_type_failure(self):
        try:
            assert_that(self.t1).is_less_than(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be <timedelta>, but was <int>')

    def test_is_less_than_or_equal_to(self):
        assert_that(self.t1).is_less_than_or_equal_to(self.t1)

    def test_is_less_than_or_equal_to_failure(self):
        try:
            t2 = datetime.timedelta(seconds=90)
            assert_that(t2).is_less_than_or_equal_to(self.t1)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{1,2}:\d{2}:\d{2}> to be less than or equal to <\d{1,2}:\d{2}:\d{2}>, but was not.')

    def test_is_less_than_or_equal_to_bad_arg_type_failure(self):
        try:
            assert_that(self.t1).is_less_than_or_equal_to(123)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given arg must be <timedelta>, but was <int>')

    def test_is_between(self):
        d2 = datetime.timedelta(seconds=90)
        d3 = datetime.timedelta(seconds=120)
        assert_that(d2).is_between(self.t1, d3)

    def test_is_between_failure(self):
        try:
            d2 = datetime.timedelta(seconds=30)
            d3 = datetime.timedelta(seconds=40)
            assert_that(self.t1).is_between(d2, d3)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).matches('Expected <\d{1,2}:\d{2}:\d{2}> to be between <\d{1,2}:\d{2}:\d{2}> and <\d{1,2}:\d{2}:\d{2}>, but was not.')
