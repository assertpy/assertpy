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

    def test_is_length(self):
        assert_that({ 'a':1,'b':2 }).is_length(2)

    def test_is_length_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).is_length(4)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to be of length <4>, but was <3>.")
            return
        self.fail('should not fail')

    def test_contains(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains('a')
        assert_that({ 'a':1,'b':2,'c':3 }).contains('a','b')

    def test_contains_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('one or more args must be given')
            return
        self.fail('should not fail')

    def test_contains_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains('x')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain item <x>, but did not.")
            return
        self.fail('should not fail')

    def test_contains_multi_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains('a','x','z')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain items ('a', 'x', 'z'), but did not contain <x>.")
            return
        self.fail('should not fail')

    def test_contains_key(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains_key('a')
        assert_that({ 'a':1,'b':2,'c':3 }).contains_key('a','b')

    def test_contains_key_bad_val_failure(self):
        try:
            assert_that(123).contains_key(1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a dict')
            return
        self.fail('should not fail')

    def test_contains_key_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_key('x')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain item <x>, but did not.")
            return
        self.fail('should not fail')

    def test_contains_key_multi_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_key('a','x','z')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain items ('a', 'x', 'z'), but did not contain <x>.")
            return
        self.fail('should not fail')

    def test_does_not_contain(self):
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x')
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x','y')

    def test_does_not_contain_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('one or more args must be given')
            return
        self.fail('should not fail')

    def test_does_not_contain_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('a')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to not contain item <a>, but did.")
            return
        self.fail('should not fail')

    def test_does_not_contain_list_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x','y','a')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to not contain items ('x', 'y', 'a'), but did contain <a>.")
            return
        self.fail('should not fail')

    def test_is_empty(self):
        assert_that({}).is_empty()

    def test_is_empty_failure(self):
        try:
            assert_that({ 'a':1,'b':2 }).is_empty()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'b': 2}> to be empty, but was not.")
            return
        self.fail('should not fail')

    def test_is_not_empty(self):
        assert_that({'a':1,'b':2}).is_not_empty()
        assert_that({'a','b'}).is_not_empty()

    def test_is_not_empty_failure(self):
        try:
            assert_that({}).is_not_empty()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected not empty, but was empty.')
            return
        self.fail('should not fail')

    def test_contains_value(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1)
        assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1,2)

    def test_contains_value_bad_val_failure(self):
        try:
            assert_that('foo').contains_value('x')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a dict')
            return
        self.fail('should not fail')

    def test_contains_value_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_value(4)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain value <4>, but did not.")
            return
        self.fail('should not fail')

    def test_contains_value_multi_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1,4,5)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain value <4>, but did not.")
            return
        self.fail('should not fail')

    def test_contains_entry(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 })
        assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'b':2 })

    def test_contains_entry_bad_val_failure(self):
        try:
            assert_that('foo').contains_entry({ 'a':1 })
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a dict')
            return
        self.fail('should not fail')

    def test_contains_entry_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('one or more entry args must be given')
            return
        self.fail('should not fail')

    def test_contains_entry_bad_arg_type_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry('x')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given entry arg must be a dict')
            return
        self.fail('should not fail')

    def test_contains_entry_bad_arg_too_big_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1, 'b':2 })
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given entry args must contain exactly one key-value pair')
            return
        self.fail('should not fail')

    def test_contains_entry_bad_key_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'x':1 })
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain entry {'x': 1}, but did not contain key <x>.")
            return
        self.fail('should not fail')

    def test_contains_entry_bad_value_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':2 })
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain entry {'a': 2}, but key <a> did not contain value <2>.")
            return
        self.fail('should not fail')

    def test_contains_entry_bad_keys_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'x':2 })
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain entry {'x': 2}, but did not contain key <x>.")
            return
        self.fail('should not fail')

    def test_contains_entry_bad_values_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'b':4 })
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <{'a': 1, 'c': 3, 'b': 2}> to contain entry {'b': 4}, but key <b> did not contain value <4>.")
            return
        self.fail('should not fail')
