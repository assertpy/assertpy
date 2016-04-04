from assertpy import assert_that,fail

class TestSet(object):

    def test_val_type_error(self):
        try:
            assert_that(1).is_subset_of(set([1,2]))
            fail('should have raised TypeError')
        except TypeError:
            pass

    def test_arg_type_error(self):
        try:
            assert_that(set([])).is_subset_of(None)
            fail('should have raised TypeError')
        except TypeError:
            pass

    def test_val_edge_case(self):
        assert_that(set()).is_subset_of(set([1,2,3]))

    def test_arg_edge_case(self):
        try:
            assert_that(set([1,2,3])).is_subset_of(set())
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected <set([1, 2, 3])> to be a subset of <set([])>, but was not.')

    def test_positive_normal_case(self):
        assert_that(set([1])).is_subset_of(set([1,2,3]))

    def test_negative_normal_case(self):
        try:
            assert_that(set([1,2,3])).is_subset_of(set([1]))
            fail('should have raised error')
        except AssertionError as ex:
            assert_that(str(ex)).is_equal_to('Expected <set([1, 2, 3])> to be a subset of <set([1])>, but was not.')

