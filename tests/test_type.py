import types
from assertpy import assert_that

class TestType(object):
    
    def testIsTypeOf(self):
        assert_that('foo').is_type_of(str)
        assert_that(123).is_type_of(int)
        assert_that(0.456).is_type_of(float)
        assert_that(234L).is_type_of(long)
        assert_that(['a','b']).is_type_of(list)
        assert_that(('a','b')).is_type_of(tuple)
        assert_that({ 'a':1,'b':2 }).is_type_of(dict)
        assert_that({ 'a','b' }).is_type_of(set)
        assert_that(None).is_type_of(types.NoneType)
        assert_that(Foo()).is_type_of(Foo)
        assert_that(Bar()).is_type_of(Bar)
    
    def testIsTypeOfFailure(self):
        try:
            assert_that('foo').is_type_of(int)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo:str> to be of type <int>, but was not.')
            return
        self.fail('should not fail')

    def testIsTypeOfBadArgFailure(self):
        try:
            assert_that('foo').is_type_of('bad')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be a type')
            return
        self.fail('should not fail')

    def testIsTypeOfSubClassFailure(self):
        try:
            assert_that(Bar()).is_type_of(Foo)
        except AssertionError, ex:
            assert_that(ex.message).starts_with('Expected <')
            assert_that(ex.message).ends_with(':Bar> to be of type <Foo>, but was not.')
            return
        self.fail('should not fail')
        
    def testIsInstanceOf(self):
        assert_that('foo').is_instance_of(str)
        assert_that(123).is_instance_of(int)
        assert_that(0.456).is_instance_of(float)
        assert_that(234L).is_instance_of(long)
        assert_that(['a','b']).is_instance_of(list)
        assert_that(('a','b')).is_instance_of(tuple)
        assert_that({ 'a':1,'b':2 }).is_instance_of(dict)
        assert_that({ 'a','b' }).is_instance_of(set)
        assert_that(None).is_instance_of(types.NoneType)
        assert_that(Foo()).is_instance_of(Foo)
        assert_that(Bar()).is_instance_of(Bar)
        assert_that(Bar()).is_instance_of(Foo)
   
    def testIsInstanceOfFailure(self):
        try:
            assert_that('foo').is_instance_of(int)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo:str> to be instance of class <int>, but was not.')
            return
        self.fail('should not fail')

    def testIsInstanceOfBadArgFailure(self):
        try:
            assert_that('foo').is_instance_of('bad')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be a class')
            return
        self.fail('should not fail')

class Foo(object):
    pass

class Bar(Foo):
    pass

