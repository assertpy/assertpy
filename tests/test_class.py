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

import types
from assertpy import assert_that

class TestClass(object):
    
    def setup(self):
        self.fred = Person('Fred','Smith')
        self.joe = Developer('Joe','Coder')
        self.people = [self.fred, self.joe]

    def testIsTypeOf(self):
        assert_that(self.fred).is_type_of(Person)
        assert_that(self.joe).is_type_of(Developer)

    def testIsInstanceOf(self):
        assert_that(self.fred).is_instance_of(Person)
        assert_that(self.fred).is_instance_of(object)

        assert_that(self.joe).is_instance_of(Developer)
        assert_that(self.joe).is_instance_of(Person)
        assert_that(self.joe).is_instance_of(object)

    def testExtractAttribute(self):
        assert_that(self.people).extract('first_name').is_equal_to(['Fred','Joe'])
        assert_that(self.people).extract('first_name').contains('Fred','Joe')

    def testExtractProperty(self):
        assert_that(self.people).extract('name').contains('Fred Smith','Joe Coder')

    def testExtractMultiple(self):
        assert_that(self.people).extract('first_name', 'name').contains(('Fred','Fred Smith'), ('Joe','Joe Coder'))

    def testExtractZeroArgMethod(self):
        assert_that(self.people).extract('say_hello').contains('Hello, Fred!', 'Joe writes code.')

    def testReadme(self):
        fred = Person('Fred','Smith')

        assert_that(fred).is_not_none()
        assert_that(fred).is_true()
        assert_that(fred).is_type_of(Person)
        assert_that(fred).is_instance_of(object)

        assert_that(fred.first_name).is_equal_to('Fred')
        assert_that(fred.name).is_equal_to('Fred Smith')
        assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')

        joe = Developer('Joe','Coder')
        people = [fred, joe]

        assert_that(people).extract('first_name').is_equal_to(['Fred','Joe'])
        assert_that(people).extract('first_name').contains('Fred','Joe')
        assert_that(people).extract('first_name', 'name').contains(('Fred','Fred Smith'), ('Joe','Joe Coder'))
        assert_that(people).extract('say_hello').contains('Hello, Fred!', 'Joe writes code.')

        assert_that(people).is_type_of(list).is_length(2).extract('first_name').contains('Fred','Joe').does_not_contain('Charlie')

class Person(object):
    def __init__(self, first_name, last_name):
        self.first_name = first_name
        self.last_name = last_name

    @property
    def name(self):
        return '%s %s' % (self.first_name, self.last_name)

    def say_hello(self):
        return 'Hello, %s!' % self.first_name

class Developer(Person):
    def say_hello(self):
        return '%s writes code.' % self.first_name
