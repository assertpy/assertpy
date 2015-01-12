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

class TestEquals(object):

    def test_is_equal(self):
        assert_that('foo').is_equal_to('foo')
        assert_that(123).is_equal_to(123)
        assert_that(0.11).is_equal_to(0.11)
        assert_that(['a','b']).is_equal_to(['a','b'])
        assert_that((1,2,3)).is_equal_to((1,2,3))
        assert_that(1 == 1).is_equal_to(True)
        assert_that(1 == 2).is_equal_to(False)
        assert_that({ 'a','b' }).is_equal_to({ 'b','a' })
        assert_that({ 'a':1,'b':2 }).is_equal_to({ 'b':2,'a':1 })

    def test_is_equal_failure(self):
        try:
            assert_that('foo').is_equal_to('bar')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to be equal to <bar>, but was not.')
            return
        self.fail('should not fail')

    def test_is_equal_int_failure(self):
        try:
            assert_that(123).is_equal_to(234)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be equal to <234>, but was not.')
            return
        self.fail('should not fail')

    def test_is_equal_list_failure(self):
        try:
            assert_that(['a','b']).is_equal_to(['a','b','c'])
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b']> to be equal to <['a', 'b', 'c']>, but was not.")
            return
        self.fail('should not fail')

    def test_is_not_equal(self):
        assert_that('foo').is_not_equal_to('bar')
        assert_that(123).is_not_equal_to(234)
        assert_that(0.11).is_not_equal_to(0.12)
        assert_that(['a','b']).is_not_equal_to(['a','x'])
        assert_that(['a','b']).is_not_equal_to(['a'])
        assert_that(['a','b']).is_not_equal_to(['a','b','c'])
        assert_that((1,2,3)).is_not_equal_to((1,2))
        assert_that(1 == 1).is_not_equal_to(False)
        assert_that(1 == 2).is_not_equal_to(True)
        assert_that({ 'a','b' }).is_not_equal_to({ 'a' })
        assert_that({ 'a':1,'b':2 }).is_not_equal_to({ 'a':1,'b':3 })
        assert_that({ 'a':1,'b':2 }).is_not_equal_to({ 'a':1,'c':2 })

    def test_is_not_equal_failure(self):
        try:
            assert_that('foo').is_not_equal_to('foo')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to be not equal to <foo>, but was.')
            return
        self.fail('should not fail')

    def test_is_not_equal_int_failure(self):
        try:
            assert_that(123).is_not_equal_to(123)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be not equal to <123>, but was.')
            return
        self.fail('should not fail')

    def test_is_not_equal_list_failure(self):
        try:
            assert_that(['a','b']).is_not_equal_to(['a','b'])
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b']> to be not equal to <['a', 'b']>, but was.")
            return
        self.fail('should not fail')
