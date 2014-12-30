from assertpy import assert_that

class TestBool(object):
    
    def testIsTrue(self):
        assert_that(True).is_true()
        assert_that(1 == 1).is_true()
        assert_that(1).is_true()
    
    def testIsTrueFailure(self):
        try:
            assert_that(False).is_true()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <True>, but was not.')
            return
        self.fail('should not fail')

    def testIsFalse(self):
        assert_that(False).is_false()
        assert_that(1 == 2).is_false()
        assert_that(0).is_false()
        assert_that([]).is_false()
        assert_that({}).is_false()
        assert_that(()).is_false()
    
    def testIsFalseFailure(self):
        try:
            assert_that(True).is_false()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <False>, but was not.')
            return
        self.fail('should not fail')

