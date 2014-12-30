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

class TestList(object):
    
    def testHasLength(self):
        assert_that(['a','b','c']).has_length(3)
        assert_that((1,2,3,4)).has_length(4)
        assert_that({ 'a':1,'b':2 }).has_length(2)
        assert_that({ 'a','b' }).has_length(2)
    
    def testHasLengthFailure(self):
        try:
            assert_that(['a','b','c']).has_length(4)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b', 'c']> to be of length <4>, but was <3>.")
            return
        self.fail('should not fail')
            
    def testHasLengthBadArgFailure(self):
        try:
            assert_that(['a','b','c']).has_length('bar')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be an int')
            return
        self.fail('should not fail')

    def testHasLengthNegativeArgFailure(self):
        try:
            assert_that(['a','b','c']).has_length(-1)
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given arg must be a positive int')
            return
        self.fail('should not fail')

    def testContains(self):
        assert_that(['a','b','c']).contains('a')
        assert_that(['a','b','c']).contains('c','b','a')
        assert_that((1,2,3,4)).contains(1,2,3)
        assert_that((1,2,3,4)).contains(4)
        assert_that({ 'a':1,'b':2,'c':3 }).contains('a')
        assert_that({ 'a':1,'b':2,'c':3 }).contains('a','b')
        assert_that({ 'a','b','c' }).contains('a')
        assert_that({ 'a','b','c' }).contains('c','b')
    
    def testContainsSingleItemFailure(self):
        try:
            assert_that(['a','b','c']).contains('x')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b', 'c']> to contain item <x>, but did not.")
            return
        self.fail('should not fail')
    
    def testContainsMultiItemFailure(self):
        try:
            assert_that(['a','b','c']).contains('a','x','z')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b', 'c']> to contain items ('a', 'x', 'z'), but did not contain <x>.")
            return
        self.fail('should not fail')

    def testDoesNotContain(self):
        assert_that(['a','b','c']).does_not_contain('x')
        assert_that(['a','b','c']).does_not_contain('x','y')
        assert_that((1,2,3,4)).does_not_contain(5)
        assert_that((1,2,3,4)).does_not_contain(5,6)
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x')
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x','y')
        assert_that({ 'a','b','c' }).does_not_contain('x')
        assert_that({ 'a','b','c' }).does_not_contain('x','y')
    
    def testDoesNotContainSingleItemFailure(self):
        try:
            assert_that(['a','b','c']).does_not_contain('a')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b', 'c']> to not contain item <a>, but did.")
            return
        self.fail('should not fail')

    def testDoesNotContainListItemFailure(self):
        try:
            assert_that(['a','b','c']).does_not_contain('x','y','a')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b', 'c']> to not contain items ('x', 'y', 'a'), but did contain <a>.")
            return
        self.fail('should not fail')

    def testIsEmpty(self):
        assert_that([]).is_empty()
        assert_that(()).is_empty()
        assert_that({}).is_empty()
        
    def testIsEmptyFailure(self):
        try:
            assert_that(['a','b']).is_empty()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b']> to be empty, but was not.")
            return
        self.fail('should not fail')

    def testIsNotEmpty(self):
        assert_that(['a','b']).is_not_empty()
        assert_that((1,2)).is_not_empty()
        assert_that({'a':1,'b':2}).is_not_empty()
        assert_that({'a','b'}).is_not_empty()
        
    def testIsNotEmptyFailure(self):
        try:
            assert_that([]).is_not_empty()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected not empty, but was empty.')
            return
        self.fail('should not fail')

    def testAssertChaining(self):
        assert_that(['a','b','c']).is_type_of(list).has_length(3).contains('a').does_not_contain('x')
        assert_that(['a','b','c']).is_type_of(list).has_length(3).contains('a','b').does_not_contain('x','y')

