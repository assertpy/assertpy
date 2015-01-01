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

class TestDict(object):
    
    def testHasLength(self):
        assert_that({ 'a':1,'b':2 }).is_length(2)
    
    def testHasLengthFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).is_length(4)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to be of length <4>, but was <3>.")
            return
        self.fail('should not fail')

    def testContains(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains('a')
        assert_that({ 'a':1,'b':2,'c':3 }).contains('a','b')

    def testContainsEmptyArgFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('one or more args must be given')
            return
        self.fail('should not fail')
        
    def testContainsSingleItemFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains('x')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain item <x>, but did not.")
            return
        self.fail('should not fail')
    
    def testContainsMultiItemFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains('a','x','z')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain items ('a', 'x', 'z'), but did not contain <x>.")
            return
        self.fail('should not fail')
        
    def testDoesNotContain(self):
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x')
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x','y')

    def testDoesNotContainEmptyArgFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('one or more args must be given')
            return
        self.fail('should not fail')

    def testDoesNotContainSingleItemFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('a')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to not contain item <a>, but did.")
            return
        self.fail('should not fail')

    def testDoesNotContainListItemFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x','y','a')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to not contain items ('x', 'y', 'a'), but did contain <a>.")
            return
        self.fail('should not fail')

    def testIsEmpty(self):
        assert_that({}).is_empty()
        
    def testIsEmptyFailure(self):
        try:
            assert_that({ 'a':1,'b':2 }).is_empty()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'b': 2}> to be empty, but was not.")
            return
        self.fail('should not fail')

    def testIsNotEmpty(self):
        assert_that({'a':1,'b':2}).is_not_empty()
        assert_that({'a','b'}).is_not_empty()
        
    def testIsNotEmptyFailure(self):
        try:
            assert_that({}).is_not_empty()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected not empty, but was empty.')
            return
        self.fail('should not fail')
        
    def testContainsValue(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1)
        assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1,2)
    
    def testContainsValueBadValFailure(self):
        try:
            assert_that('foo').contains_value('x')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not dict')
            return
        self.fail('should not fail')
    
    def testContainsValueSingleItemFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_value(4)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain value <4>, but did not.")
            return
        self.fail('should not fail')
    
    def testContainsValueMultiItemFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1,4,5)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain value <4>, but did not.")
            return
        self.fail('should not fail')

    def testContainsEntry(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 })
        assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'b':2 })
    
    def testContainsEntryBadValFailure(self):
        try:
            assert_that('foo').contains_entry({ 'a':1 })
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not dict')
            return
        self.fail('should not fail')

    def testContainsEntryEmptyArgFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('one or more entry args must be given')
            return
        self.fail('should not fail')
        
    def testContainsEntryBadArgTypeFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry('x')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given entry arg must be dict')
            return
        self.fail('should not fail')

    def testContainsEntryBadArgTooBigFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1, 'b':2 })
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given entry args must contain exactly one key-value pair')
            return
        self.fail('should not fail')

    def testContainsEntrySingleEntryKeyFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'x':1 })
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain entry {'x': 1}, but did not contain key <x>.")
            return
        self.fail('should not fail')
    
    def testContainsEntrySingleEntryValueFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':2 })
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain entry {'a': 2}, but key <a> did not contain value <2>.")
            return
        self.fail('should not fail')
        
    def testContainsEntryMultiEntryKeyFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'x':2 })
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain entry {'x': 2}, but did not contain key <x>.")
            return
        self.fail('should not fail')

    def testContainsEntryMultiEntryValueFailure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'b':4 })
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain entry {'b': 4}, but key <b> did not contain value <4>.")
            return
        self.fail('should not fail')

