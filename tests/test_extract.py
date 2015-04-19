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

from assertpy import assert_that,fail

class TestExtract(object):

    def setup(self):
        fred = Person('Fred', 'Smith', 12)
        john = Person('John', 'Jones', 9.5)
        self.people = [fred, john]

    def test_extract_property(self):
        assert_that(self.people).extract('first_name').contains('Fred','John')

    def test_extract_multiple_properties(self):
        assert_that(self.people).extract('first_name', 'last_name', 'shoe_size').contains(('Fred','Smith',12), ('John','Jones',9.5))

    def test_extract_zero_arg_method(self):
        assert_that(self.people).extract('full_name').contains('Fred Smith', 'John Jones')

    def test_extract_property_and_method(self):
        assert_that(self.people).extract('first_name', 'full_name').contains(('Fred','Fred Smith'), ('John', 'John Jones'))

    def test_extract_bad_val_failure(self):
        try:
            assert_that('foo').extract('bar')
            fail('should have raised error')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not a collection')

    def test_extract_empty_args_failure(self):
        try:
            assert_that(self.people).extract()
            fail('should have raised error')
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('one or more name args must be given')

    def test_extract_bad_property_failure(self):
        try:
            assert_that(self.people).extract('foo')
            fail('should have raised error')
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('val does not have property or zero-arg method <foo>')

    def test_extract_too_many_args_method_failure(self):
        try:
            assert_that(self.people).extract('say_hello')
            fail('should have raised error')
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('val method <say_hello()> exists, but is not zero-arg method')

class Person(object):
    def __init__(self, first_name, last_name, shoe_size):
        self.first_name = first_name
        self.last_name = last_name
        self.shoe_size = shoe_size

    def full_name(self):
        return '%s %s' % (self.first_name, self.last_name)

    def say_hello(self, name):
        return 'Hello, %s!' % name
