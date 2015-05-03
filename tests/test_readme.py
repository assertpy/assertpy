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
import datetime
from assertpy import assert_that,contents_of,fail

class TestNumbers(object):

    def setup(self):
        with open('foo.txt', 'w') as fp:
            fp.write('foobar')

    def teardown(self):
        os.remove('foo.txt')

    def test_something(self):
        assert_that(1 + 2).is_equal_to(3)
        assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')

    def test_strings(self):
        assert_that('').is_not_none()
        assert_that('').is_empty()
        assert_that('').is_false()
        assert_that('').is_type_of(str)
        assert_that('').is_instance_of(str)

        assert_that('foo').is_length(3)
        assert_that('foo').is_not_empty()
        assert_that('foo').is_true()
        assert_that('foo').is_alpha()
        assert_that('123').is_digit()
        assert_that('foo').is_lower()
        assert_that('FOO').is_upper()
        assert_that('foo').is_equal_to('foo')
        assert_that('foo').is_not_equal_to('bar')
        assert_that('foo').is_equal_to_ignoring_case('FOO')

        assert_that('foo').contains('f')
        assert_that('foo').contains('f','oo')
        assert_that('foo').does_not_contain('x')
        assert_that('foo').contains_sequence('o','o')

        assert_that('foo').contains_duplicates()
        assert_that('fox').does_not_contain_duplicates()

        assert_that('foo').is_in('foo','bar','baz')
        assert_that('foo').is_not_in('boo','bar','baz')

        assert_that('foo').starts_with('f')
        assert_that('foo').ends_with('oo')

        assert_that('foo').matches(r'\w')
        assert_that('123-456-7890').matches(r'\d{3}-\d{3}-\d{4}')
        assert_that('foo').does_not_match(r'\d+')

        # partial matches, these all pass
        assert_that('foo').matches(r'\w')
        assert_that('foo').matches(r'oo')
        assert_that('foo').matches(r'\w{2}')

        # match the entire string with an anchored regex pattern, passes
        assert_that('foo').matches(r'^\w{3}$')

        # fails
        try:
            assert_that('foo').matches(r'^\w{2}$')
            fail('should have raised error')
        except AssertionError:
            pass

    def test_ints(self):
        assert_that(0).is_not_none()
        assert_that(0).is_false()
        assert_that(0).is_type_of(int)
        assert_that(0).is_instance_of(int)

        assert_that(0).is_zero()
        assert_that(1).is_not_zero()
        assert_that(1).is_positive()
        assert_that(-1).is_negative()

        assert_that(123).is_equal_to(123)
        assert_that(123).is_not_equal_to(456)

        assert_that(123).is_greater_than(100)
        assert_that(123).is_greater_than_or_equal_to(123)
        assert_that(123).is_less_than(200)
        assert_that(123).is_less_than_or_equal_to(200)
        assert_that(123).is_between(100, 200)
        assert_that(123).is_close_to(100, 25)

        assert_that(1).is_in(0,1,2,3)
        assert_that(1).is_not_in(-1,-2,-3)


    def test_floats(self):
        assert_that(0.0).is_not_none()
        assert_that(0.0).is_false()
        assert_that(0.0).is_type_of(float)
        assert_that(0.0).is_instance_of(float)

        assert_that(123.4).is_equal_to(123.4)
        assert_that(123.4).is_not_equal_to(456.7)

        assert_that(123.4).is_greater_than(100.1)
        assert_that(123.4).is_greater_than_or_equal_to(123.4)
        assert_that(123.4).is_less_than(200.2)
        assert_that(123.4).is_less_than_or_equal_to(123.4)
        assert_that(123.4).is_between(100.1, 200.2)
        assert_that(123.4).is_close_to(123, 0.5)

    def test_lists(self):
        assert_that([]).is_not_none()
        assert_that([]).is_empty()
        assert_that([]).is_false()
        assert_that([]).is_type_of(list)
        assert_that([]).is_instance_of(list)

        assert_that(['a','b']).is_length(2)
        assert_that(['a','b']).is_not_empty()
        assert_that(['a','b']).is_equal_to(['a','b'])
        assert_that(['a','b']).is_not_equal_to(['b','a'])

        assert_that(['a','b']).contains('a')
        assert_that(['a','b']).contains('b','a')
        assert_that(['a','b']).does_not_contain('x','y')
        assert_that(['a','b','c']).contains_sequence('b','c')

        assert_that(['a','x','x']).contains_duplicates()
        assert_that(['a','b','c']).does_not_contain_duplicates()

    def test_tuples(self):
        assert_that(()).is_not_none()
        assert_that(()).is_empty()
        assert_that(()).is_false()
        assert_that(()).is_type_of(tuple)
        assert_that(()).is_instance_of(tuple)

        assert_that((1,2,3)).is_length(3)
        assert_that((1,2,3)).is_not_empty()
        assert_that((1,2,3)).is_equal_to((1,2,3))
        assert_that((1,2,3)).is_not_equal_to((1,2,4))

        assert_that((1,2,3)).contains(1)
        assert_that((1,2,3)).contains(3,2,1)
        assert_that((1,2,3)).does_not_contain(4,5,6)
        assert_that((1,2,3)).contains_sequence(2,3)

        assert_that((1,2,2)).contains_duplicates()
        assert_that((1,2,3)).does_not_contain_duplicates()

    def test_dicts(self):
        assert_that({}).is_not_none()
        assert_that({}).is_empty()
        assert_that({}).is_false()
        assert_that({}).is_type_of(dict)
        assert_that({}).is_instance_of(dict)

        assert_that({'a':1,'b':2}).is_length(2)
        assert_that({'a':1,'b':2}).is_not_empty()
        assert_that({'a':1,'b':2}).is_equal_to({'a':1,'b':2})
        assert_that({'a':1,'b':2}).is_equal_to({'b':2,'a':1})
        assert_that({'a':1,'b':2}).is_not_equal_to({'a':1,'b':3})

        assert_that({'a':1,'b':2}).contains('a')
        assert_that({'a':1,'b':2}).contains('b','a')
        assert_that({'a':1,'b':2}).does_not_contain('x')
        assert_that({'a':1,'b':2}).does_not_contain('x','y')

        # contains_key() is just an alias for contains()
        assert_that({'a':1,'b':2}).contains_key('a')
        assert_that({'a':1,'b':2}).contains_key('b','a')

        # does_not_contain_key() is just an alias for does_not_contain()
        assert_that({'a':1,'b':2}).does_not_contain_key('x')
        assert_that({'a':1,'b':2}).does_not_contain_key('x','y')

        assert_that({'a':1,'b':2}).contains_value(1)
        assert_that({'a':1,'b':2}).contains_value(2,1)
        assert_that({'a':1,'b':2}).does_not_contain_value(3)
        assert_that({'a':1,'b':2}).does_not_contain_value(3,4)

        assert_that({'a':1,'b':2}).contains_entry({'a':1})
        assert_that({'a':1,'b':2}).contains_entry({'a':1},{'b':2})
        assert_that({'a':1,'b':2}).does_not_contain_entry({'a':2})
        assert_that({'a':1,'b':2}).does_not_contain_entry({'a':2},{'b':1})

    def test_sets(self):
        assert_that(set({})).is_not_none()
        assert_that(set({})).is_empty()
        assert_that(set({})).is_false()
        assert_that(set({})).is_type_of(set)
        assert_that(set({})).is_instance_of(set)

        assert_that({'a','b'}).is_length(2)
        assert_that({'a','b'}).is_not_empty()
        assert_that({'a','b'}).is_equal_to({'a','b'})
        assert_that({'a','b'}).is_equal_to({'b','a'})
        assert_that({'a','b'}).is_not_equal_to({'a','x'})

        assert_that({'a','b'}).contains('a')
        assert_that({'a','b'}).contains('b','a')
        assert_that({'a','b'}).does_not_contain('x','y')

    def test_booleans(self):
        assert_that(True).is_true()
        assert_that(False).is_false()
        assert_that(True).is_type_of(bool)

    def test_dates(self):
        today = datetime.datetime.today()
        yesterday = today - datetime.timedelta(days=1)

        assert_that(yesterday).is_before(today)
        assert_that(today).is_after(yesterday)

        today_0us = today - datetime.timedelta(microseconds=today.microsecond)
        today_0s = today - datetime.timedelta(seconds=today.second)
        today_0h = today - datetime.timedelta(hours=today.hour)

        assert_that(today).is_equal_to_ignoring_milliseconds(today_0us)
        assert_that(today).is_equal_to_ignoring_seconds(today_0s)
        assert_that(today).is_equal_to_ignoring_time(today_0h)
        assert_that(today).is_equal_to(today)

        middle = today - datetime.timedelta(hours=12)
        hours_24 = datetime.timedelta(hours=24)

        assert_that(today).is_greater_than(yesterday)
        assert_that(yesterday).is_less_than(today)
        assert_that(middle).is_between(yesterday, today)

        #note that the tolerance must be a datetime.timedelta object
        assert_that(yesterday).is_close_to(today, hours_24)

        # 1980-01-02 03:04:05.000006
        x = datetime.datetime(1980, 1, 2, 3, 4, 5, 6)

        assert_that(x).has_year(1980)
        assert_that(x).has_month(1)
        assert_that(x).has_day(2)
        assert_that(x).has_hour(3)
        assert_that(x).has_minute(4)
        assert_that(x).has_second(5)
        assert_that(x).has_microsecond(6)

    def test_files(self):
        assert_that('foo.txt').exists()
        assert_that('foo.txt').is_file()

        #assert_that('mydir').exists()
        #assert_that('mydir').is_directory()

        assert_that('foo.txt').is_named('foo.txt')
        #assert_that('foo.txt').is_child_of('mydir')

        assert_that(contents_of('foo.txt')).starts_with('foo').ends_with('bar').contains('oob')

    def test_objects(self):
        fred = Person('Fred','Smith')

        assert_that(fred).is_not_none()
        assert_that(fred).is_true()
        assert_that(fred).is_type_of(Person)
        assert_that(fred).is_instance_of(object)

        assert_that(fred.first_name).is_equal_to('Fred')
        assert_that(fred.name).is_equal_to('Fred Smith')
        assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')

        fred = Person('Fred','Smith')
        bob = Person('Bob','Barr')
        people = [fred, bob]

        assert_that(people).extract('first_name').is_equal_to(['Fred','Bob'])
        assert_that(people).extract('first_name').contains('Fred','Bob')
        assert_that(people).extract('first_name').does_not_contain('Charlie')

        fred = Person('Fred','Smith')
        joe = Developer('Joe','Coder')
        people = [fred, joe]

        assert_that(people).extract('first_name').contains('Fred','Joe')

        assert_that(people).extract('first_name', 'last_name').contains(('Fred','Smith'), ('Joe','Coder'))

        assert_that(people).extract('name').contains('Fred Smith', 'Joe Coder')
        assert_that(people).extract('say_hello').contains('Hello, Fred!', 'Joe writes code.')

    def test_dyn(self):
        fred = Person('Fred','Smith')

        assert_that(fred.first_name).is_equal_to('Fred')
        assert_that(fred.name).is_equal_to('Fred Smith')
        assert_that(fred.say_hello()).is_equal_to('Hello, Fred!')

        assert_that(fred).has_first_name('Fred')
        assert_that(fred).has_name('Fred Smith')
        assert_that(fred).has_say_hello('Hello, Fred!')

    def test_chaining(self):
        fred = Person('Fred','Smith')
        joe = Person('Joe','Jones')
        people = [fred, joe]

        assert_that('foo').is_length(3).starts_with('f').ends_with('oo')

        assert_that([1,2,3]).is_type_of(list).contains(1,2).does_not_contain(4,5)

        assert_that(fred).has_first_name('Fred').has_last_name('Smith').has_shoe_size(12)

        assert_that(people).is_length(2).extract('first_name').contains('Fred','Joe')

class Person(object):
    def __init__(self, first_name, last_name, shoe_size = 12):
        self.first_name = first_name
        self.last_name = last_name
        self.shoe_size = shoe_size

    @property
    def name(self):
        return '%s %s' % (self.first_name, self.last_name)

    def say_hello(self):
        return 'Hello, %s!' % self.first_name

class Developer(Person):
    def say_hello(self):
        return '%s writes code.' % self.first_name
