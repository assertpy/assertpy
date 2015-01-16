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

import datetime
from assertpy import assert_that

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
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be before <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')
            return
        self.fail('should not fail')

    def test_is_before_bad_val_type_failure(self):
        try:
            assert_that(123).is_before(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_before_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_before(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_after(self):
        d2 = datetime.datetime.today()
        assert_that(d2).is_after(self.d1)

    def test_is_after_failure(self):
        try:
            d2 = datetime.datetime.today()
            assert_that(self.d1).is_after(d2)
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be after <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')
            return
        self.fail('should not fail')

    def test_is_after_bad_val_type_failure(self):
        try:
            assert_that(123).is_after(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_after_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_after(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_milliseconds(self):
        assert_that(self.d1).is_equal_to_ignoring_milliseconds(self.d1)

    def test_is_equal_to_ignoring_milliseconds_failure(self):
        try:
            d2 = datetime.datetime.today() + datetime.timedelta(days=1)
            assert_that(self.d1).is_equal_to_ignoring_milliseconds(d2)
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}> to be equal to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}>, but was not.')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_milliseconds_bad_val_type_failure(self):
        try:
            assert_that(123).is_equal_to_ignoring_milliseconds(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_milliseconds_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_equal_to_ignoring_milliseconds(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_seconds(self):
        assert_that(self.d1).is_equal_to_ignoring_seconds(self.d1)

    def test_is_equal_to_ignoring_seconds_failure(self):
        try:
            d2 = datetime.datetime.today() + datetime.timedelta(days=1)
            assert_that(self.d1).is_equal_to_ignoring_seconds(d2)
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected <\d{4}-\d{2}-\d{2} \d{2}:\d{2}> to be equal to <\d{4}-\d{2}-\d{2} \d{2}:\d{2}>, but was not.')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_seconds_bad_val_type_failure(self):
        try:
            assert_that(123).is_equal_to_ignoring_seconds(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_seconds_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_equal_to_ignoring_seconds(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_time(self):
        assert_that(self.d1).is_equal_to_ignoring_time(self.d1)

    def test_is_equal_to_ignoring_time_failure(self):
        try:
            d2 = datetime.datetime.today() + datetime.timedelta(days=1)
            assert_that(self.d1).is_equal_to_ignoring_time(d2)
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected <\d{4}-\d{2}-\d{2}> to be equal to <\d{4}-\d{2}-\d{2}>, but was not.')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_time_bad_val_type_failure(self):
        try:
            assert_that(123).is_equal_to_ignoring_time(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val must be datetime, but was type <int>')
            return
        self.fail('should not fail')

    def test_is_equal_to_ignoring_time_bad_arg_type_failure(self):
        try:
            assert_that(self.d1).is_equal_to_ignoring_time(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be datetime, but was type <int>')
            return
        self.fail('should not fail')
