# Copyright (c) 2015-2018, Activision Publishing, Inc.
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

import sys
import collections

from assertpy import assert_that,fail


def test_is_iterable():
    assert_that(['a','b','c']).is_iterable()
    assert_that((1,2,3)).is_iterable()
    assert_that('foo').is_iterable()
    assert_that({ 'a':1,'b':2,'c':3 }.keys()).is_iterable()
    assert_that({ 'a':1,'b':2,'c':3 }.values()).is_iterable()
    assert_that({ 'a':1,'b':2,'c':3 }.items()).is_iterable()

def test_is_iterable_failure():
    try:
        assert_that(123).is_iterable()
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to('Expected iterable, but was not.')

def test_is_not_iterable():
    assert_that(123).is_not_iterable()
    assert_that({ 'a':1,'b':2,'c':3 }).is_iterable()

def test_is_not_iterable_failure():
    try:
        assert_that(['a','b','c']).is_not_iterable()
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to('Expected not iterable, but was.')

def test_is_subset_of():
    assert_that(['a','b','c']).is_subset_of(['a','b','c'])
    assert_that(['a','b','c']).is_subset_of(['a','b','c','d'])
    assert_that(['a','b','c']).is_subset_of(['a'], ['b'], ['c'])
    assert_that(['a','b','c']).is_subset_of('a','b','c')
    assert_that(['a','b','a']).is_subset_of(['a','a','b'])
    assert_that((1,2,3)).is_subset_of((1,2,3))
    assert_that((1,2,3)).is_subset_of((1,2,3,4))
    assert_that((1,2,3)).is_subset_of((1,), (2,), (3,))
    assert_that((1,2,3)).is_subset_of(1,2,3)
    assert_that((1,2,1)).is_subset_of(1,1,2)
    assert_that('foo').is_subset_of('abcdefghijklmnopqrstuvwxyz')
    assert_that('foo').is_subset_of('abcdef', set(['m','n','o']), ['x','y'])
    assert_that(set([1,2,3])).is_subset_of(set([1,2,3,4]))
    assert_that({'a':1,'b':2}).is_subset_of({'a':1,'b':2,'c':3})
    assert_that({'a':1,'b':2}).is_subset_of({'a':3}, {'b':2}, {'a':1})

def test_is_subset_of_failure_array():
    try:
        assert_that(['a','b','c']).is_subset_of(['a','b'])
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).contains('but <c> was missing.')

def test_is_subset_of_failure_set():
    try:
        assert_that(set([1,2,3])).is_subset_of(set([1,2]))
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).contains('but <3> was missing.')

def test_is_subset_of_failure_string():
    try:
        assert_that('abc').is_subset_of('abx')
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).contains('but <c> was missing.')

def test_is_subset_of_failure_dict_key():
    try:
        assert_that({'a':1,'b':2}).is_subset_of({'a':1,'c':3})
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).contains("but <{'b': 2}> was missing")

def test_is_subset_of_failure_dict_value():
    try:
        assert_that({'a':1,'b':2}).is_subset_of({'a':1,'b':22})
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).contains("but <{'b': 2}> was missing.")

def test_is_subset_of_failure_bad_dict_arg1():
    try:
        assert_that({'a':1,'b':2}).is_subset_of('foo')
        fail('should have raised error')
    except TypeError as ex:
        assert_that(str(ex)).contains('arg #1').contains('is not dict-like')

def test_is_subset_of_failure_bad_dict_arg2():
    try:
        assert_that({'a':1,'b':2}).is_subset_of({'a':1}, 'foo')
        fail('should have raised error')
    except TypeError as ex:
        assert_that(str(ex)).contains('arg #2').contains('is not dict-like')

def test_is_subset_of_bad_val_failure():
    try:
        assert_that(123).is_subset_of(1234)
        fail('should have raised error')
    except TypeError as ex:
        assert_that(str(ex)).is_equal_to('val is not iterable')

def test_is_subset_of_bad_arg_failure():
    try:
        assert_that(['a','b','c']).is_subset_of()
        fail('should have raised error')
    except ValueError as ex:
        assert_that(str(ex)).is_equal_to('one or more superset args must be given')

def test_chaining():
    assert_that(['a','b','c']).is_iterable().is_type_of(list).is_length(3)

