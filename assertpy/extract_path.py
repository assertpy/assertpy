# Copyright (c) 2015-2019, Activision Publishing, Inc.
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

import sys
import collections
from typing import Hashable

if sys.version_info[0] == 3:
    str_types = (str,)
    Iterable = collections.abc.Iterable
else:
    str_types = (basestring,)
    Iterable = collections.Iterable

__tracebackhide__ = True


class ExtractPathMixin(object):
    """
    Path extracting mixin.

    It is often necessary to test responses in json format, or mixed dictionary/list/user-defined-object/et blobs
    validating specific entries, in various response paths. Use the ``extract_path()`` helper to access such
    entries while at the same time validating path expectations. Extract values at different paths from a
    mixed dict/list/user-obj blob:

        example_nested_blob = [
            True, False, {
                'anything_1': ('a', 'b', 'c'),
                'instance': SomeUserDefinedClass(
                    name='Fred',
                    age=32,
                    children={
                        'Bob': 3,
                        'Alice': 5,
                    }
                ),
                'anything_2': 66
            }, None,
        ]

        assert_that(example_nested_blob).extract_path(1).is_equal_to(False)
        assert_that(example_nested_blob).extract_path(2, 'anything_1').is_length(3).extract_path(1).is_equal_to('b')
        assert_that(example_nested_blob).extract_path(2, 'anything_2').is_equal_to(66)
        assert_that(example_nested_blob).extract_path(2, 'instance', 'name').is_equal_to('Fred')
        assert_that(example_nested_blob).extract_path(2, 'instance', 'children').has_Bob(3).has_Alice(5)
    """
    def extract_path(self, *keys):
        """Asserts that each of keys is index, key or attribute of the corresponding val layer, then extracts
        element at final layer.

        Args:
            *keys: the keys forming the path to extraction.

        Examples:
            Usage::
                example_nested_blob = [
                    True, False, {
                        'anything_1': ('a', 'b', 'c'),
                        'instance': SomeUserDefinedClass(
                            name='Fred',
                            age=32,
                            children={
                                'Bob': 3,
                                'Alice': 5,
                            }
                        ),
                        'anything_2': 66
                    }, None,
                ]

                assert_that(example_nested_blob).extract_path(1).is_equal_to(False)
                assert_that(example_nested_blob).extract_path(2, 'anything_2').is_equal_to(66)
                assert_that(example_nested_blob).extract_path(2, 'instance', 'name').is_equal_to('Fred')
                assert_that(example_nested_blob).extract_path(2, 'instance', 'children').has_Bob(3).has_Alice(5)

            Works with list/tuple/range, dict-like & user-object types.

            Allows chaining extractions while doing validations along the path::

                assert_that(example_nested_blob).extract_path(2, 'anything_1').is_length(3).extract_path(1).is_equal_to('b')

        Returns:
            AssertionBuilder: returns a new instance (now with the extracted element as the val) to chain to the next assertion

        Raises:
            AssertionError: if any of the given keys representing path is **not** index, key or attribute of the corresponding val layer
        """
        for path_depth, key in enumerate(keys):
            if isinstance(key, int) and isinstance(self.val, (list, tuple, range)):
                if not -len(self.val) <= key < len(self.val):
                    self.error('Expected index <%i> to be in range of iterable value at path depth %i, but was not.' % (key, path_depth))
                self.val = self.val[key]
            elif isinstance(key, Hashable) and self._check_dict_like(self.val, return_as_bool=True): # isinstance(self.val, dict):
                try:
                    self.val = self.val[key]
                except KeyError:
                    self.error('Expected key <%s> to be in dict keys of value at path depth %i, but was not.' % (key, path_depth))
            elif isinstance(key, str) and hasattr(self.val, key):
                self.val = getattr(self.val, key)
            else:
                self.error('Expected key <%s> to be valid extraction key for value at path depth %i, but was not.' % (key, path_depth))

        return self


