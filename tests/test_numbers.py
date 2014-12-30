from assertpy import assert_that

class TestNumbers(object):
    
    def testIsGreaterThan(self):
        assert_that(123).is_greater_than(100)
        assert_that(123).is_greater_than(0)
        assert_that(123).is_greater_than(-100)
        assert_that(123).is_greater_than(122.5)
    
    def testIsGreaterThanFailure(self):
        try:
            assert_that(123).is_greater_than(1000)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be greater than <1000>, but was not.')
            return
        self.fail('should not fail')

    def testIsGreaterThanBadValueTypeFailure(self):
        try:
            assert_that('foo').is_greater_than(0)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not numeric')
            return
        self.fail('should not fail')
        
    def testIsGreaterThanBadArgTypeFailure(self):
        try:
            assert_that(123).is_greater_than('foo')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be numeric')
            return
        self.fail('should not fail')

    def testIsLessThan(self):
        assert_that(123).is_less_than(1000)
        assert_that(123).is_less_than(1e6)
        assert_that(-123).is_less_than(-100)
        assert_that(123).is_less_than(123.001)
    
    def testIsLessThanFailure(self):
        try:
            assert_that(123).is_less_than(1)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be less than <1>, but was not.')
            return
        self.fail('should not fail')

    def testIsLessThanBadValueTypeFailure(self):
        try:
            assert_that('foo').is_less_than(0)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not numeric')
            return
        self.fail('should not fail')
        
    def testIsLessThanBadArgTypeFailure(self):
        try:
            assert_that(123).is_less_than('foo')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be numeric')
            return
        self.fail('should not fail')

    def testIsBetween(self):
        assert_that(123).is_between(120,125)
        assert_that(123).is_between(0,1e6)
        assert_that(-123).is_between(-150,-100)
        assert_that(123).is_between(122.999,123.001)
    
    def testIsBetweenFailure(self):
        try:
            assert_that(123).is_between(0,1)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be between <0> and <1>, but was not.')
            return
        self.fail('should not fail')

    def testIsBetweenBadValueTypeFailure(self):
        try:
            assert_that('foo').is_between(0,1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not numeric')
            return
        self.fail('should not fail')
        
    def testIsBetweenBadLowArgTypeFailure(self):
        try:
            assert_that(123).is_between('foo',1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given low arg must be numeric')
            return
        self.fail('should not fail')
        
    def testIsBetweenBadHighArgTypeFailure(self):
        try:
            assert_that(123).is_between(0,'foo')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given high arg must be numeric')
            return
        self.fail('should not fail')

    def testIsBetweenBadArgDeltaFailure(self):
        try:
            assert_that(123).is_between(1,0)
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given low arg must be less than given high arg')
            return
        self.fail('should not fail')

    def testIsCloseTo(self):
        assert_that(123.01).is_close_to(123,1)
        assert_that(0.01).is_close_to(0,1)
        assert_that(-123.01).is_close_to(-123,1)
    
    def testIsCloseToFailure(self):
        try:
            assert_that(123.01).is_close_to(100,1)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123.01> to be close to <100> within tolerance <1>, but was not.')
            return
        self.fail('should not fail')

    def testIsCloseToBadValueTypeFailure(self):
        try:
            assert_that('foo').is_close_to(123,1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not numeric')
            return
        self.fail('should not fail')
        
    def testIsCloseToBadValueArgTypeFailure(self):
        try:
            assert_that(123.01).is_close_to('foo',1)
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given arg must be numeric')
            return
        self.fail('should not fail')
        
    def testIsCloseToBadToleranceArgTypeFailure(self):
        try:
            assert_that(123.01).is_close_to(0,'foo')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('given tolerance arg must be numeric')
            return
        self.fail('should not fail')

    def testIsCloseToBadToleranceNegativeFailure(self):
        try:
            assert_that(123.01).is_close_to(123,-1)
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('given tolerance arg must be positive')
            return
        self.fail('should not fail')

    def testAssertChaining(self):
        assert_that(123).is_greater_than(100).is_less_than(1000).is_between(120,125).is_close_to(100,25)

