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

import os
import tempfile
from assertpy import assert_that,contents_of,fail

class TestFile(object):

    def setup(self):
        self.tmp = tempfile.NamedTemporaryFile()
        self.tmp.write('foobar')
        self.tmp.seek(0)

    def teardown(self):
        print 'TEARDOWN: closing %s' % self.tmp.name
        self.tmp.close()

    def test_contents_of_path(self):
        contents = contents_of(self.tmp.name)
        assert_that(contents).is_equal_to('foobar').starts_with('foo').ends_with('bar')

    def test_contents_of_file(self):
        contents = contents_of(self.tmp.file)
        assert_that(contents).is_equal_to('foobar').starts_with('foo').ends_with('bar')

    def test_contains_of_bad_type_failure(self):
        try:
            contents_of(123)
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('val must be file or path, but was type <int>')
            return
        fail('should not fail')

    def test_exists(self):
        assert_that(self.tmp.name).exists()
        print dir(self.tmp)

    def test_exists_failure(self):
        try:
            assert_that('missing.txt').exists()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <missing.txt> to exist, but not found.')
            return
        fail('should not fail')

    def test_exists_bad_val_failure(self):
        try:
            assert_that(123).exists()
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a path')
            return
        fail('should not fail')

    def test_is_file(self):
        assert_that(self.tmp.name).is_file()

    def test_is_file_exists_failure(self):
        try:
            assert_that('missing.txt').is_file()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <missing.txt> to exist, but not found.')
            return
        fail('should not fail')

    def test_is_file_directory_failure(self):
        try:
            dirname = os.path.dirname(self.tmp.name)
            assert_that(dirname).is_file()
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected <.*> to be a file, but was not.')
            return
        fail('should not fail')

    def test_is_directory(self):
        dirname = os.path.dirname(self.tmp.name)
        assert_that(dirname).is_directory()

    def test_is_directory_exists_failure(self):
        try:
            assert_that('missing_dir').is_directory()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <missing_dir> to exist, but not found.')
            return
        fail('should not fail')

    def test_is_directory_file_failure(self):
        try:
            assert_that(self.tmp.name).is_directory()
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected <.*> to be a directory, but was not.')
            return
        fail('should not fail')

    def test_is_named(self):
        basename = os.path.basename(self.tmp.name)
        assert_that(self.tmp.name).is_named(basename)

    def test_is_named_failure(self):
        try:
            assert_that(self.tmp.name).is_named('foo.txt')
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected filename <.*> to be equal to <foo.txt>, but was not.')
            return
        fail('should not fail')

    def test_is_named_bad_arg_type_failure(self):
        try:
            assert_that(self.tmp.name).is_named(123)
        except TypeError, ex:
            assert_that(ex.message).matches('given filename arg must be a path')
            return
        fail('should not fail')

    def test_is_child_of(self):
        dirname = os.path.dirname(self.tmp.name)
        assert_that(self.tmp.name).is_child_of(dirname)

    def test_is_child_of_failure(self):
        try:
            assert_that(self.tmp.name).is_child_of('foo_dir')
        except AssertionError, ex:
            assert_that(ex.message).matches('Expected file <.*> to be a child of <.*/foo_dir>, but was not.')
            return
        fail('should not fail')

    def test_is_child_of_bad_arg_type_failure(self):
        try:
            assert_that(self.tmp.name).is_child_of(123)
        except TypeError, ex:
            assert_that(ex.message).matches('given parent directory arg must be a path')
            return
        fail('should not fail')
