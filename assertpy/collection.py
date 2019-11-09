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
import operator
import sys
import collections

if sys.version_info[0] == 3:
    Iterable = collections.abc.Iterable
else:
    Iterable = collections.Iterable


class CollectionMixin(object):
    """Collection assertions mixin."""

    def is_iterable(self):
        """Asserts that val is iterable collection."""
        if not isinstance(self.val, Iterable):
            self._err('Expected iterable, but was not.')
        return self

    def is_not_iterable(self):
        """Asserts that val is not iterable collection."""
        if isinstance(self.val, Iterable):
            self._err('Expected not iterable, but was.')
        return self

    def is_subset_of(self, *supersets):
        """Asserts that val is iterable and a subset of the given superset or flattened superset if multiple supersets are given."""
        if not isinstance(self.val, Iterable):
            raise TypeError('val is not iterable')
        if len(supersets) == 0:
            raise ValueError('one or more superset args must be given')

        missing = []
        if hasattr(self.val, 'keys') and callable(getattr(self.val, 'keys')) and hasattr(self.val, '__getitem__'):
            # flatten superset dicts
            superdict = {}
            for l,j in enumerate(supersets):
                self._check_dict_like(j, check_values=False, name='arg #%d' % (l+1))
                for k in j.keys():
                    superdict.update({k: j[k]})

            for i in self.val.keys():
                if i not in superdict:
                    missing.append({i: self.val[i]}) # bad key
                elif self.val[i] != superdict[i]:
                    missing.append({i: self.val[i]}) # bad val
            if missing:
                self._err('Expected <%s> to be subset of %s, but %s %s missing.' % (self.val, self._fmt_items(superdict), self._fmt_items(missing), 'was' if len(missing) == 1 else 'were'))
        else:
            # flatten supersets
            superset = set()
            for j in supersets:
                try:
                    for k in j:
                        superset.add(k)
                except Exception:
                    superset.add(j)

            for i in self.val:
                if i not in superset:
                    missing.append(i)
            if missing:
                self._err('Expected <%s> to be subset of %s, but %s %s missing.' % (self.val, self._fmt_items(superset), self._fmt_items(missing), 'was' if len(missing) == 1 else 'were'))

        return self

    def is_sorted(self, compare_op=operator.ge):
        """Asserts that value is sorted by at least one of the provided compare functions."""

        # Make compare_op a list
        try:
            self._check_iterable(compare_op)
            compare_ops = compare_op
        except TypeError as e:
            compare_ops = [compare_op]

        # Loop through compare_ops and find two unsorted items.
        op_it = iter(compare_ops)
        sorted_by_any = False

        while not sorted_by_any:
            try:
                op = next(op_it)
            except StopIteration as si:
                break

            sorted_by_any = True

            for i in range(len(self.val) - 1):
                if not op(self.val[i + 1], self.val[i]):
                    sorted_by_any = False
                    break

        if not sorted_by_any:
            self._err('Expected value to be sorted by any of %s, but was not.' % str(compare_ops))

        return self