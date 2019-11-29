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

if sys.version_info[0] == 3:
    str_types = (str,)
    Iterable = collections.abc.Iterable
else:
    str_types = (basestring,)
    Iterable = collections.Iterable


class ExtractingMixin(object):
    """Collection flattening mixin."""

    def extracting(self, *names, **kwargs):
        """Asserts that val is iterable, then extracts the named props or named zero-arg methods into a list (or list of tuples if multiple names are given)."""
        if not isinstance(self.val, Iterable):
            raise TypeError('val is not iterable')
        if isinstance(self.val, str_types):
            raise TypeError('val must not be string')
        if len(names) == 0:
            raise ValueError('one or more name args must be given')

        def _extract(x, name):
            if self._check_dict_like(x, check_values=False, return_as_bool=True):
                if name in x:
                    return x[name]
                else:
                    raise ValueError('item keys %s did not contain key <%s>' % (list(x.keys()), name))
            elif isinstance(x, Iterable):
                self._check_iterable(x, name='item')
                return x[name]
            elif hasattr(x, name):
                attr = getattr(x, name)
                if callable(attr):
                    try:
                        return attr()
                    except TypeError:
                        raise ValueError('val method <%s()> exists, but is not zero-arg method' % name)
                else:
                    return attr
            else:
                raise ValueError('val does not have property or zero-arg method <%s>' % name)

        def _filter(x):
            if 'filter' in kwargs:
                if isinstance(kwargs['filter'], str_types):
                    return bool(_extract(x, kwargs['filter']))
                elif self._check_dict_like(kwargs['filter'], check_values=False, return_as_bool=True):
                    for k in kwargs['filter']:
                        if isinstance(k, str_types):
                            if _extract(x, k) != kwargs['filter'][k]:
                                return False
                    return True
                elif callable(kwargs['filter']):
                    return kwargs['filter'](x)
                return False
            return True

        def _sort(x):
            if 'sort' in kwargs:
                if isinstance(kwargs['sort'], str_types):
                    return _extract(x, kwargs['sort'])
                elif isinstance(kwargs['sort'], Iterable):
                    items = []
                    for k in kwargs['sort']:
                        if isinstance(k, str_types):
                            items.append(_extract(x, k))
                    return tuple(items)
                elif callable(kwargs['sort']):
                    return kwargs['sort'](x)
            return 0

        extracted = []
        for i in sorted(self.val, key=lambda x: _sort(x)):
            if _filter(i):
                items = [_extract(i, name) for name in names]
                extracted.append(tuple(items) if len(items) > 1 else items[0])

        # chain on with _extracted_ list (don't chain to self!)
        return self._builder(extracted, self.description, self.kind)
