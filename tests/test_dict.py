# Copyright (c) 2015-2016, Activision Publishing, Inc.
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

from assertpy import assert_that,fail

class TestDict(object):

    def test_is_length(self):
        assert_that({ 'a':1,'b':2 }).is_length(2)

    def test_is_length_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).is_length(4)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to be of length <4>, but was <3>.')

    def test_contains(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains('a')
        assert_that({ 'a':1,'b':2,'c':3 }).contains('a','b')

    def test_contains_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains()
            fail('should have raised error')
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to('one or more args must be given')

    def test_contains_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains('x')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to contain key <x>, but did not.')

    def test_contains_multi_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains('a','x','z')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain keys ('a', 'x', 'z'), but did not contain key <x>.")

    def test_contains_key(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains_key('a')
        assert_that({ 'a':1,'b':2,'c':3 }).contains_key('a','b')

    def test_contains_key_bad_val_failure(self):
        try:
            assert_that(123).contains_key(1)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val is not dict-like')

    def test_does_not_contain_key(self):
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_key('x')
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_key('x','y')

    def test_does_not_contain_key_bad_val_failure(self):
        try:
            assert_that(123).does_not_contain_key(1)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val is not dict-like')

    def test_contains_key_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_key('x')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to contain key <x>, but did not.')

    def test_contains_key_multi_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_key('a','x','z')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain keys ('a', 'x', 'z'), but did not contain key <x>.")

    def test_does_not_contain(self):
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x')
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x','y')

    def test_does_not_contain_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain()
            fail('should have raised error')
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to('one or more args must be given')

    def test_does_not_contain_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('a')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to not contain item <a>, but did.')

    def test_does_not_contain_list_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain('x','y','a')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to not contain items ('x', 'y', 'a'), but did contain <a>.")

    def test_is_empty(self):
        assert_that({}).is_empty()

    def test_is_empty_failure(self):
        try:
            assert_that({ 'a':1,'b':2 }).is_empty()
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to be empty, but was not.')

    def test_is_not_empty(self):
        assert_that({'a':1,'b':2}).is_not_empty()
        assert_that(set(['a','b'])).is_not_empty()

    def test_is_not_empty_failure(self):
        try:
            assert_that({}).is_not_empty()
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected not empty, but was empty.')

    def test_contains_value(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1)
        assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1,2)

    def test_contains_value_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_value()
            fail('should have raised error')
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to('one or more value args must be given')

    def test_contains_value_bad_val_failure(self):
        try:
            assert_that('foo').contains_value('x')
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val is not dict-like')

    def test_contains_value_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_value(4)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to contain value <4>, but did not.')

    def test_contains_value_multi_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_value(1,4,5)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to contain value <4>, but did not.')

    def test_does_not_contain_value(self):
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_value(4)
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_value(4,5)

    def test_does_not_contain_value_bad_val_failure(self):
        try:
            assert_that(123).does_not_contain_value(1)
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val is not dict-like')

    def test_does_not_contain_value_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_value()
            fail('should have raised error')
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to('one or more value args must be given')

    def test_does_not_contain_value_single_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_value(1)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to not contain value <1>, but did.')

    def test_does_not_contain_value_list_item_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_value(4,5,1)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('to not contain values (4, 5, 1), but did contain <1>.')

    def test_contains_entry(self):
        assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 })
        assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'b':2 })

    def test_contains_entry_bad_val_failure(self):
        try:
            assert_that('foo').contains_entry({ 'a':1 })
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val is not dict-like')

    def test_contains_entry_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry()
            fail('should have raised error')
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to('one or more entry args must be given')

    def test_contains_entry_bad_arg_type_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry('x')
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given entry arg must be a dict')

    def test_contains_entry_bad_arg_too_big_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1, 'b':2 })
            fail('should have raised error')
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to('given entry args must contain exactly one key-value pair')

    def test_contains_entry_bad_key_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'x':1 })
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain entry {'x': 1}, but did not contain key <x>.")

    def test_contains_entry_bad_value_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':2 })
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain entry {'a': 2}, but key <a> did not contain value <2>.")

    def test_contains_entry_bad_keys_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'x':2 })
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain entry {'x': 2}, but did not contain key <x>.")

    def test_contains_entry_bad_values_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).contains_entry({ 'a':1 },{ 'b':4 })
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to contain entry {'b': 4}, but key <b> did not contain value <4>.")

    def test_does_not_contain_entry(self):
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_entry({ 'a':2 })
        assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_entry({ 'a':2 },{ 'b':1 })

    def test_does_not_contain_entry_bad_val_failure(self):
        try:
            assert_that('foo').does_not_contain_entry({ 'a':1 })
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val is not dict-like')

    def test_does_not_contain_entry_empty_arg_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_entry()
            fail('should have raised error')
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to('one or more entry args must be given')

    def test_does_not_contain_entry_bad_arg_type_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_entry('x')
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('given entry arg must be a dict')

    def test_does_not_contain_entry_bad_arg_too_big_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_entry({ 'a':1, 'b':2 })
            fail('should have raised error')
        except ValueError as ex:
            assert_that(str(ex)).is_equal_to('given entry args must contain exactly one key-value pair')

    def test_does_not_contain_entry_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_entry({ 'a':1 })
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to not contain entry {'a': 1}, but did.")

    def test_does_not_contain_entry_multiple_failure(self):
        try:
            assert_that({ 'a':1,'b':2,'c':3 }).does_not_contain_entry({ 'a':2 },{ 'b':2 })
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains("to not contain entry {'b': 2}, but did.")

    def test_contains_sub_dict_bad_val_failure(self):
        try:
            assert_that('foo').contains_sub_dict({'a': 1})
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val is not dict-like')

    def test_contains_sub_dict_bad_sub_dict_value_failure(self):
        try:
            assert_that({'a': 1}).contains_sub_dict('foo')
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('sub dict is not dict-like')

    def test_contains_sub_dict(self):
        assert_that({'a': '2', 'b': '3', 'c': '4'}).contains_sub_dict({'b': '3', 'a': '2'})

    def test_contains_sub_dict_key_mismatch(self):
        dict_val = {'a': 1, 'b': 2, 'c': 3}
        sub_dict_val = {'d': 1}
        try:
            assert_that(dict_val).contains_sub_dict(sub_dict_val)
            fail('should have raised error')
        except AssertionError as ex:
            dict_str = str(dict_val)
            sub_dict_str = str(sub_dict_val)
            msg = ('Expected {0} to contain {1} '
                   'but did not contain all keys and/or key/value pairs').format(dict_val,
                                                                                 sub_dict_str)
            assert_that(str(ex)).is_equal_to(msg)

    def test_contains_sub_dict_value_mismatch(self):
        dict_val = {'a': 1, 'b': 2, 'c': 3}
        sub_dict_val = {'a': 0}
        try:
            assert_that(dict_val).contains_sub_dict(sub_dict_val)
            fail('should have raised error')
        except AssertionError as ex:
            dict_str = str(dict_val)
            sub_dict_str = str(sub_dict_val)
            msg = ('Expected {0} to contain {1} '
                   'but did not contain all keys and/or key/value pairs').format(dict_val,
                                                                                 sub_dict_str)
            assert_that(str(ex)).is_equal_to(msg)

    def test_does_not_contain_sub_dict_bad_val_failure(self):
        try:
            assert_that('foo').does_not_contain_sub_dict({'a': 1})
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('val is not dict-like')

    def test_does_not_contain_sub_dict_bad_sub_dict_value_failure(self):
        try:
            assert_that({'a': 1}).contains_sub_dict('foo')
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).is_equal_to('sub dict is not dict-like')

    def test_does_not_contain_sub_dict_failure(self):
        dict_val = {'a': 1, 'b': 2, 'c': 3}
        sub_dict_val = {'a': 1}
        try:
            assert_that(dict_val).does_not_contain_sub_dict(sub_dict_val)
            fail('should have raised error')
        except AssertionError as ex:
            dict_str = str(dict_val)
            sub_dict_str = str(sub_dict_val)
            msg = ('Expected {0} to not contain sub dict {1}, '
                   'but found one or more key and value matches.').format(dict_str, sub_dict_str)
            assert_that(str(ex)).contains(msg)

    def test_does_not_contain_sub_dict(self):
        dict_val = {'a': 1, 'b': 2, 'c': 3}
        assert_that(dict_val).does_not_contain_sub_dict({'d': 1})
