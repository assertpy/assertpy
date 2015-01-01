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

class TestString(object):
    
    def testHasLength(self):
        assert_that('foo').is_length(3)
    
    def testHasLengthFailure(self):
        try:
            assert_that('foo').is_length(4)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to be of length <4>, but was <3>.')
            return
        self.fail('should not fail')

    def testContains(self):
        assert_that('foo').contains('f')
        assert_that('foo').contains('o')
        assert_that('foo').contains('fo','o')
        assert_that('fred').contains('d')
        assert_that('fred').contains('fr','e','d')
    
    def testContainsSingleItemFailure(self):
        try:
            assert_that('foo').contains('x')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to contain item <x>, but did not.')
            return
        self.fail('should not fail')
    
    def testContainsMultiItemFailure(self):
        try:
            assert_that('foo').contains('f','x','z')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <foo> to contain items ('f', 'x', 'z'), but did not contain <x>.")
            return
        self.fail('should not fail')

    def testDoesNotContain(self):
        assert_that('foo').does_not_contain('x')
        assert_that('foo').does_not_contain('x','y')
    
    def testDoesNotContainSingleItemFailure(self):
        try:
            assert_that('foo').does_not_contain('f')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to not contain item <f>, but did.')
            return
        self.fail('should not fail')

    def testDoesNotContainListItemFailure(self):
        try:
            assert_that('foo').does_not_contain('x','y','f')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <foo> to not contain items ('x', 'y', 'f'), but did contain <f>.")
            return
        self.fail('should not fail')

    def testIsEmpty(self):
        assert_that('').is_empty()
        
    def testIsEmptyFailure(self):
        try:
            assert_that('foo').is_empty()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to be empty string, but was not.')
            return
        self.fail('should not fail')

    def testIsNotEmpty(self):
        assert_that('foo').is_not_empty()
        
    def testIsNotEmptyFailure(self):
        try:
            assert_that('').is_not_empty()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected not empty string, but was empty.')
            return
        self.fail('should not fail')

    def testIsEqualIgnoringCase(self):
        assert_that('FOO').is_equal_to_ignoring_case('foo')
        assert_that('foo').is_equal_to_ignoring_case('FOO')
        assert_that('fOO').is_equal_to_ignoring_case('foo')
    
    def testIsEqualIgnoringCaseFailure(self):
        try:
            assert_that('foo').is_equal_to_ignoring_case('bar')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to be case-insensitive equal to <bar>, but was not.')
            return
        self.fail('should not fail')

    def testIsEqualIgnoringWithBadValueTypeFailure(self):
        try:
            assert_that(123).is_equal_to_ignoring_case(12)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a string')
            return
        self.fail('should not fail')

    def testIsEqualIgnoringWithBadArgTypeFailure(self):
        try:
            assert_that('fred').is_equal_to_ignoring_case(12)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be a string')
            return
        self.fail('should not fail')

    def testStartsWith(self):
        assert_that('fred').starts_with('f')
        assert_that('fred').starts_with('fr')
        assert_that('fred').starts_with('fred')
    
    def testStartsWithFailure(self):
        try:
            assert_that('fred').starts_with('bar')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <fred> to start with <bar>, but did not.')
            return
        self.fail('should not fail')

    def testStartsWithBadValueTypeFailure(self):
        try:
            assert_that(123).starts_with(12)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a string')
            return
        self.fail('should not fail')
        
    def testStartsWithBadArgTypeFailure(self):
        try:
            assert_that('fred').starts_with(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given prefix arg must be a string')
            return
        self.fail('should not fail')
        
    def testStartsWithBadArgEmptyFailure(self):
        try:
            assert_that('fred').starts_with('')
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given prefix arg must not be empty')
            return
        self.fail('should not fail')

    def testEndsWith(self):
        assert_that('fred').ends_with('d')
        assert_that('fred').ends_with('ed')
        assert_that('fred').ends_with('fred')

    def testEndsWithFailure(self):
        try:
            assert_that('fred').ends_with('bar')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <fred> to end with <bar>, but did not.')
            return
        self.fail('should not fail')

    def testEndsWithBadValueTypeFailure(self):
        try:
            assert_that(123).ends_with(12)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a string')
            return
        self.fail('should not fail')
        
    def testEndsWithBadArgTypeFailure(self):
        try:
            assert_that('fred').ends_with(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given suffix arg must be a string')
            return
        self.fail('should not fail')
        
    def testEndsWithBadArgEmptyFailure(self):
        try:
            assert_that('fred').ends_with('')
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given suffix arg must not be empty')
            return
        self.fail('should not fail')

    def testMatches(self):
        assert_that('fred').matches('\w')
        assert_that('fred').matches('\w{2}')
        assert_that('fred').matches('\w+')
        assert_that('fred').matches('^\w{4}$')
        assert_that('fred').matches('^.*?$')
        assert_that('123-456-7890').matches('\d{3}-\d{3}-\d{4}')

    def testMatchesFailure(self):
        try:
            assert_that('fred').matches('\d+')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <fred> to match pattern <\d+>, but did not.')
            return
        self.fail('should not fail')

    def testMatchesBadValueTypeFailure(self):
        try:
            assert_that(123).matches(12)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a string')
            return
        self.fail('should not fail')
        
    def testMatchesBadArgTypeFailure(self):
        try:
            assert_that('fred').matches(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given pattern arg must be a string')
            return
        self.fail('should not fail')
        
    def testMatchesBadArgEmptyFailure(self):
        try:
            assert_that('fred').matches('')
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given pattern arg must not be empty')
            return
        self.fail('should not fail')

    def testDoesNotMatch(self):
        assert_that('fred').does_not_match('\d+')
        assert_that('fred').does_not_match('\w{5}')
        assert_that('123-456-7890').does_not_match('^\d+$')

    def testDoesNotMatchFailure(self):
        try:
            assert_that('fred').does_not_match('\w+')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <fred> to not match pattern <\w+>, but did.')
            return
        self.fail('should not fail')

    def testDoesNotMatchBadValueTypeFailure(self):
        try:
            assert_that(123).does_not_match(12)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a string')
            return
        self.fail('should not fail')
        
    def testDoesNotMatchBadArgTypeFailure(self):
        try:
            assert_that('fred').does_not_match(123)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given pattern arg must be a string')
            return
        self.fail('should not fail')
        
    def testDoesNotMatchBadArgEmptyFailure(self):
        try:
            assert_that('fred').does_not_match('')
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given pattern arg must not be empty')
            return
        self.fail('should not fail')

    def testIsAlpha(self):
        assert_that('foo').is_alpha()

    def testIsAlphaFailureWithDigits(self):
        try:
            assert_that('foo123').is_alpha()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo123> to contain only alphabetic chars, but did not.')
            return
        self.fail('should not fail')

    def testIsAlphaFailureWithSpaces(self):
        try:
            assert_that('foo bar').is_alpha()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo bar> to contain only alphabetic chars, but did not.')
            return
        self.fail('should not fail')

    def testIsAlphaFailureWithPunctuation(self):
        try:
            assert_that('foo,bar').is_alpha()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo,bar> to contain only alphabetic chars, but did not.')
            return
        self.fail('should not fail')

    def testIsAlphaBadValueTypeFailure(self):
        try:
            assert_that(123).is_alpha()
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a string')
            return
        self.fail('should not fail')

    def testIsAlphaEmptyValueFailure(self):
        try:
            assert_that('').is_alpha()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('val is empty')
            return
        self.fail('should not fail')

    def testIsDigit(self):
        assert_that('123').is_digit()

    def testIsDigitFailureWithAlpha(self):
        try:
            assert_that('foo123').is_digit()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo123> to contain only digits, but did not.')
            return
        self.fail('should not fail')

    def testIsDigitFailureWithSpaces(self):
        try:
            assert_that('1 000 000').is_digit()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <1 000 000> to contain only digits, but did not.')
            return
        self.fail('should not fail')

    def testIsDigitFailureWithPunctuation(self):
        try:
            assert_that('-123').is_digit()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <-123> to contain only digits, but did not.')
            return
        self.fail('should not fail')

    def testIsDigitBadValueTypeFailure(self):
        try:
            assert_that(123).is_digit()
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a string')
            return
        self.fail('should not fail')

    def testIsDigitEmptyValueFailure(self):
        try:
            assert_that('').is_digit()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('val is empty')
            return
        self.fail('should not fail')

    def testAssertChaining(self):
        assert_that('foo').is_type_of(str).is_length(3).contains('f').does_not_contain('x')
        assert_that('fred').starts_with('f').ends_with('d').matches('^f.*?d$').does_not_match('\d')
