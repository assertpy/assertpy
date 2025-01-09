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
    """
    def extract_path(self, *keys):
        """
        Extracts element at path pointed by keys, from object value.
        Verifies each key validity and presence.
        """
        for path_depth, key in enumerate(keys):
            if isinstance(key, int) and isinstance(self.val, (list, tuple, range)):
                if not -len(self.val) <= key < len(self.val):
                    raise ValueError('index <%i> is out of value range at path depth %i' % (key, path_depth))
                self.val = self.val[key]
            elif isinstance(key, Hashable) and isinstance(self.val, dict):
                if key not in self.val:
                    raise ValueError('key <%s> is not in dict keys at path depth %i' % (key, path_depth))
                self.val = self.val[key]
            elif isinstance(key, str) and hasattr(self.val, key):
                self.val = eval(f'self.val.{key}')
            else:
                raise ValueError('invalid extraction key <%s> for value at path depth %i' % (key, path_depth))

        return self


