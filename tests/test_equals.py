from assertpy import assert_that

class TestEquals(object):
    
    def testIsEqual(self):
        assert_that('foo').is_equal_to('foo')
        assert_that(123).is_equal_to(123)
        assert_that(0.11).is_equal_to(0.11)
        assert_that(['a','b']).is_equal_to(['a','b'])
        assert_that((1,2,3)).is_equal_to((1,2,3))
        assert_that(1 == 1).is_equal_to(True)
        assert_that(1 == 2).is_equal_to(False)
        assert_that({ 'a','b' }).is_equal_to({ 'b','a' })
        assert_that({ 'a':1,'b':2 }).is_equal_to({ 'b':2,'a':1 })
    
    def testIsEqualFailure(self):
        try:
            assert_that('foo').is_equal_to('bar')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to be equal to <bar>, but was not.')
            return
        self.fail('should not fail')

    def testIsEqualIntFailure(self):
        try:
            assert_that(123).is_equal_to(234)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be equal to <234>, but was not.')
            return
        self.fail('should not fail')

    def testIsEqualListFailure(self):
        try:
            assert_that(['a','b']).is_equal_to(['a','b','c'])
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b']> to be equal to <['a', 'b', 'c']>, but was not.")
            return
        self.fail('should not fail')

    def testIsNotEqual(self):
        assert_that('foo').is_not_equal_to('bar')
        assert_that(123).is_not_equal_to(234)
        assert_that(0.11).is_not_equal_to(0.12)
        assert_that(['a','b']).is_not_equal_to(['a','x'])
        assert_that(['a','b']).is_not_equal_to(['a'])
        assert_that(['a','b']).is_not_equal_to(['a','b','c'])
        assert_that((1,2,3)).is_not_equal_to((1,2))
        assert_that(1 == 1).is_not_equal_to(False)
        assert_that(1 == 2).is_not_equal_to(True)
        assert_that({ 'a','b' }).is_not_equal_to({ 'a' })
        assert_that({ 'a':1,'b':2 }).is_not_equal_to({ 'a':1,'b':3 })
        assert_that({ 'a':1,'b':2 }).is_not_equal_to({ 'a':1,'c':2 })
    
    def testIsNotEqualFailure(self):
        try:
            assert_that('foo').is_not_equal_to('foo')
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <foo> to be not equal to <foo>, but was.')
            return
        self.fail('should not fail')

    def testIsNotEqualIntFailure(self):
        try:
            assert_that(123).is_not_equal_to(123)
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to('Expected <123> to be not equal to <123>, but was.')
            return
        self.fail('should not fail')

    def testIsNotEqualListFailure(self):
        try:
            assert_that(['a','b']).is_not_equal_to(['a','b'])
        except AssertionError, ex:
            assert_that(ex.message).is_equal_to("Expected <['a', 'b']> to be not equal to <['a', 'b']>, but was.")
            return
        self.fail('should not fail')

