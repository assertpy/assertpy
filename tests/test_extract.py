from assertpy import assert_that

class TestExtract(object):
        
    def setup(self):
        fred = Person('Fred', 'Smith', 12)
        john = Person('John', 'Jones', 9.5)
        self.people = [fred, john]

    def testExtractProperty(self):
        assert_that(self.people).extract('first_name').contains('Fred','John')

    def testExtractMultipleProperties(self):
        assert_that(self.people).extract('first_name', 'last_name', 'shoe_size').contains(('Fred','Smith',12), ('John','Jones',9.5))
        
    def testExtractZeroArgMethod(self):
        assert_that(self.people).extract('full_name').contains('Fred Smith', 'John Jones')

    def testExtractPropertyAndMethod(self):
        assert_that(self.people).extract('first_name', 'full_name').contains(('Fred','Fred Smith'), ('John', 'John Jones'))
        
    def testExtractBadValFailure(self):
        try:
            assert_that('foo').extract('bar')
        except TypeError, ex:
            assert_that(ex.message).is_equal_to('val is not collection')
            return
        self.fail('should not fail')

    def testExtractEmptyArgsFailure(self):
        try:
            assert_that(self.people).extract()
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('one or more name args must be given')
            return
        self.fail('should not fail')
        
    def testExtractBadPropertyFailure(self):
        try:
            assert_that(self.people).extract('foo')
        except ValueError, ex:
            assert_that(ex.message).is_equal_to('val does not have property or zero-arg method <foo>')
            return
        self.fail('should not fail')
        
class Person(object):
    def __init__(self, first_name, last_name, shoe_size):
        self.first_name = first_name
        self.last_name = last_name
        self.shoe_size = shoe_size
        
    def full_name(self):
        return '%s %s' % (self.first_name, self.last_name)

