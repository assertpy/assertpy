# Copyright (c) 2015-2021, Activision Publishing, Inc.
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

import collections

from assertpy import assert_that, fail


Foo = collections.namedtuple('Foo', ['bar', 'baz'])
foo = Foo(bar='abc', baz=123)
foos = [foo, Foo(bar='xyz', baz=456)]


def test_namedtuple_equals():
    assert_that(foo).is_instance_of(Foo)
    assert_that(foo).is_instance_of(tuple)
    assert_that(foo).is_instance_of(object)
    assert_that(foo).is_type_of(Foo)
    assert_that(foo).is_equal_to(('abc', 123))
    assert_that(foo).is_equal_to(Foo(bar='abc', baz=123))
    assert_that(foo).is_not_equal_to(Foo(bar='abc', baz=124))
    assert_that(foo.bar).is_equal_to('abc')
    assert_that(foo[0]).is_equal_to('abc')
    assert_that(foo.baz).is_equal_to(123)
    assert_that(foo[1]).is_equal_to(123)
    assert_that(foo._fields).is_equal_to(('bar', 'baz'))


def test_namedtuple_equals_failure():
    try:
        assert_that(foo).is_equal_to(Foo(bar='abc', baz=124))
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected <Foo(bar='abc', baz=123)> to be equal to <Foo(bar='abc', baz=124)>, but was not.")


def test_namedtuple_has():
    assert_that(foo).has_bar('abc')
    assert_that(foo).has_baz(123)


def test_namedtuple_has_failure():
    try:
        assert_that(foo).has_missing('x')
        fail('should have raised error')
    except AssertionError as ex:
        assert_that(str(ex)).is_equal_to("Expected attribute <missing>, but val has no attribute <missing>.")


def test_namedtuple_extracting_by_index():
    assert_that(foos).extracting(0).is_equal_to(['abc', 'xyz'])
    assert_that(foos).extracting(1).is_equal_to([123, 456])


def test_namedtuple_extracting_by_name():
    assert_that(foos).extracting('bar').is_equal_to(['abc', 'xyz'])
    assert_that(foos).extracting('baz').is_equal_to([123, 456])


def test_namedtuple_extracting_by_name_failure():
    try:
        assert_that(foos).extracting('missing').is_equal_to('x')
        fail('should have raised error')
    except ValueError as ex:
        assert_that(str(ex)).is_equal_to("item attributes ('bar', 'baz') did no contain attribute <missing>")
