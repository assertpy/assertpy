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

from collections import defaultdict, ChainMap, OrderedDict
from types import MappingProxyType

from assertpy import assert_that, fail
from pytest import mark, param


@mark.parametrize('example_iterable', [
    param([1, 2, 3], id='list'),
    param((1, 2, 3), id='tuple'),
    param(range(1, 4), id='range'),
])
class TestExtractPathMethodWithLists:
    def test_iterable_extraction(self, example_iterable):
        assert_that(example_iterable).extract_path(0).is_equal_to(1)
        assert_that(example_iterable).extract_path(2).is_equal_to(3)
        assert_that(example_iterable).extract_path().is_equal_to(example_iterable)

    def test_iterable_extraction_neg_index(self, example_iterable):
        assert_that(example_iterable).extract_path(-1).is_equal_to(3)
        assert_that(example_iterable).extract_path(-3).is_equal_to(1)

    def test_iterable_extraction_pos_index_bounds_failure(self, example_iterable):
        try:
            assert_that(example_iterable).extract_path(3)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected index <3> to be in range of iterable value at path depth 0, but was not.')

    def test_iterable_extraction_neg_index_bounds_failure(self, example_iterable):
        try:
            assert_that(example_iterable).extract_path(-4)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected index <-4> to be in range of iterable value at path depth 0, but was not.')

    def test_iterable_extraction_invalid_str_index_failure(self, example_iterable):
        try:
            assert_that(example_iterable).extract_path('1')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected key <1> to be valid extraction key for value at path depth 0, but was not.')

    def test_iterable_extraction_invalid_none_index_failure(self, example_iterable):
        try:
            assert_that(example_iterable).extract_path(None)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected key <None> to be valid extraction key for value at path depth 0, but was not.')


class TestExtractPathMethodWithDictionaries:
    def test_dict_extraction(self, ):
        assert_that({'1': 1, '2': 2, '3': 3}).extract_path('1').is_equal_to(1)
        assert_that ({'1': 1, '2': 2, '3': 3}).extract_path('3').is_equal_to(3)
        assert_that ({None: 1, '2': 2, '3': 3}).extract_path(None).is_equal_to(1)
        assert_that ({'1': 1, 55: 2, '3': 3}).extract_path(55).is_equal_to(2)
        assert_that({'1': 1, '2': 2, '3': 3}).extract_path().is_equal_to({'1': 1, '2': 2, '3': 3})

    def test_dict_like_extraction(self):
        assert_that(defaultdict(int, {'1': 1})).extract_path('1').is_equal_to(1)
        assert_that(defaultdict(int, {'1': 1})).extract_path('2').is_equal_to(0)
        assert_that(ChainMap({'a': 1}, {'b': 2})).extract_path('b').is_equal_to(2)
        assert_that(OrderedDict([('a', 1), ('b', 2)])).extract_path('b').is_equal_to(2)
        assert_that(MappingProxyType({'a': 1, 'b': 2})).extract_path('b').is_equal_to(2)

    @mark.parametrize('invalid_key', [0, '4', None])
    def test_dict_extraction_invalid_key_failure(self, invalid_key):
        try:
            assert_that({'1': 1, '2': 2, '3': 3}).extract_path(invalid_key)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected key <%s> to be in dict keys of value at path depth 0, but was not.' % invalid_key)


class ExampleClass:
    def __init__(self, name: str, age: int, children: dict):
        self.name = name
        self.age = age
        self.children = children


example_obj = ExampleClass(
    name='Fred',
    age=32,
    children={
        'Bob': 3,
        'Alice': 5
    }
)


class TestExtractPathMethodWithUserDefinedObjects:
    def test_obj_extraction(self, ):
        assert_that(example_obj).extract_path('name').is_equal_to('Fred')
        assert_that(example_obj).extract_path('age').is_equal_to(32)
        assert_that(example_obj).extract_path('children').has_Bob(3).has_Alice(5).does_not_contain('name', 'age')
        assert_that(example_obj).extract_path().is_equal_to(example_obj)

    @mark.parametrize('invalid_field', ['Age', 0, None])
    def test_obj_extraction_invalid_field_failure(self, invalid_field):
        try:
            assert_that(example_obj).extract_path(invalid_field)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected key <%s> to be valid extraction key for value at path depth 0, but was not.' % invalid_field)


example_nested_blob = [
    True, False, {
        'anything_1': ('a', 'b', 'c'),
        'instance': example_obj,
        'anything_2': 66
    }, None,
]


class TestExtractPathMethodWithNestedMixedTypeBlobs:
    def test_nested_obj_extraction(self):
        assert_that(example_nested_blob).extract_path(1).is_false()
        assert_that(example_nested_blob).extract_path(2, 'anything_2').is_equal_to(66)
        assert_that(example_nested_blob).extract_path(2, 'instance', 'name').is_equal_to('Fred')
        assert_that(example_nested_blob).extract_path(2, 'instance', 'children').has_Bob(3).has_Alice(5)
        assert_that(example_nested_blob).extract_path(2, 'instance', 'children').does_not_contain('name', 'age')

    def test_nested_obj_chained_extractions(self):
        assert_that(example_nested_blob).extract_path(2, 'anything_1').is_length(3).extract_path(1).is_equal_to('b')

    def test_nested_obj_extraction_path_end_failure(self):
        try:
            assert_that(example_nested_blob).extract_path(1, 'instance', 'name')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected key <instance> to be valid extraction key for value at path depth 1, but was not.')

    def test_nested_obj_extraction_depth_1_invalid_key_failure(self):
        try:
            assert_that(example_nested_blob).extract_path(2, 'instances', 'name')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected key <instances> to be in dict keys of value at path depth 1, but was not.')

    def test_nested_obj_extraction_depth_2_invalid_key_failure(self):
        try:
            assert_that(example_nested_blob).extract_path(2, 'instance', 'names')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected key <names> to be valid extraction key for value at path depth 2, but was not.')
