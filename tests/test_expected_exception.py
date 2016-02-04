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

from assertpy import assert_that, fail

class TestExpectedException(object):

    def test_expected_exception(self):
        assert_that(func_no_arg).raises(RuntimeError).when_called_with()
        assert_that(func_one_arg).raises(RuntimeError).when_called_with('foo')
        assert_that(func_multi_args).raises(RuntimeError).when_called_with('foo', 'bar', 'baz')
        assert_that(func_kwargs).raises(RuntimeError).when_called_with(foo=1, bar=2, baz=3)
        assert_that(func_all).raises(RuntimeError).when_called_with('a', 'b', 3, 4, foo=1, bar=2, baz='dog')

    def test_expected_exception_no_arg_failure(self):
        try:
            assert_that(func_noop).raises(RuntimeError).when_called_with()
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to(
                'Expected <func_noop> to raise <RuntimeError> when called with ().')

    def test_expected_exception_no_arg_bad_func_failure(self):
        try:
            assert_that(123).raises(int).when_called_with()
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).contains('val must be function')

    def test_expected_exception_no_arg_bad_exception_failure(self):
        try:
            assert_that(func_noop).raises(int).when_called_with()
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).contains('given arg must be exception')

    def test_expected_exception_no_arg_wrong_exception_failure(self):
        try:
            assert_that(func_no_arg).raises(TypeError).when_called_with()
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).contains('Expected <func_no_arg> to raise <TypeError> when called with (), but raised <RuntimeError>.')

    def test_expected_exception_no_arg_missing_raises_failure(self):
        try:
            assert_that(func_noop).when_called_with()
            fail('should have raised error')
        except TypeError as ex:
            assert_that(str(ex)).contains('expected exception not set, raises() must be called first')

    def test_expected_exception_one_arg_failure(self):
        try:
            assert_that(func_noop).raises(RuntimeError).when_called_with('foo')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to(
                "Expected <func_noop> to raise <RuntimeError> when called with ('foo').")

    def test_expected_exception_multi_args_failure(self):
        try:
            assert_that(func_noop).raises(RuntimeError).when_called_with('foo', 'bar', 'baz')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to("Expected <func_noop> to raise <RuntimeError> when called with ('foo', 'bar', 'baz').")

    def test_expected_exception_kwargs_failure(self):
        try:
            assert_that(func_noop).raises(RuntimeError).when_called_with(foo=1, bar=2, baz=3)
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to(
                "Expected <func_noop> to raise <RuntimeError> when called with ('bar': 2, 'baz': 3, 'foo': 1).")

    def test_expected_exception_all_failure(self):
        try:
            assert_that(func_noop).raises(RuntimeError).when_called_with('a', 'b', 3, 4, foo=1, bar=2, baz='dog')
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to(
                "Expected <func_noop> to raise <RuntimeError> when called with ('a', 'b', 3, 4, 'bar': 2, 'baz': 'dog', 'foo': 1).")

    def test_expected_exception_arg_passing(self):
        assert_that(func_all).raises(RuntimeError).when_called_with('a', 'b', 3, 4, foo=1, bar=2, baz='dog').is_equal_to(
            "all err: arg1=a, arg2=b, args=(3, 4), kwargs=[('bar', 2), ('baz', 'dog'), ('foo', 1)]")


def func_noop(*args, **kwargs):
    pass

def func_no_arg():
    raise RuntimeError('no arg err')

def func_one_arg(arg):
    raise RuntimeError('one arg err')

def func_multi_args(*args):
    raise RuntimeError('multi args err')

def func_kwargs(**kwargs):
    raise RuntimeError('kwargs err')

def func_all(arg1, arg2, *args, **kwargs):
    raise RuntimeError('all err: arg1=%s, arg2=%s, args=%s, kwargs=%s' % (arg1, arg2, args, [(k,kwargs[k]) for k in sorted(kwargs.keys())]))

