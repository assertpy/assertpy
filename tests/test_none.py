from assertpy import assert_that

class TestNone(object):
    
    def testIsNone(self):
        assert_that(None).is_none()
    
    def testIsNoneFailure(self):
        try:
            assert_that('foo').is_none()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to be <None>, but was not.')
            return
        self.fail('should not fail')

    def testIsNotNone(self):
        assert_that('foo').is_not_none()
        assert_that(123).is_not_none()
        assert_that(False).is_not_none()
        assert_that([]).is_not_none()
        assert_that({}).is_not_none()
        
    def testIsNotNoneFailure(self):
        try:
            assert_that(None).is_not_none()
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected not <None>, but was.')
            return
        self.fail('should not fail')

