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

import os
import sys

if sys.version_info[0] == 3:
    str_types = (str,)
else:
    str_types = (basestring,)


def contents_of(f, encoding='utf-8'):
    """Helper to read the contents of the given file or path into a string with the given encoding.
    Encoding defaults to 'utf-8', other useful encodings are 'ascii' and 'latin-1'."""

    try:
        contents = f.read()
    except AttributeError:
        try:
            with open(f, 'r') as fp:
                contents = fp.read()
        except TypeError:
            raise ValueError('val must be file or path, but was type <%s>' % type(f).__name__)
        except OSError:
            if not isinstance(f, str_types):
                raise ValueError('val must be file or path, but was type <%s>' % type(f).__name__)
            raise

    if sys.version_info[0] == 3 and type(contents) is bytes:
        # in PY3 force decoding of bytes to target encoding
        return contents.decode(encoding, 'replace')
    elif sys.version_info[0] == 2 and encoding == 'ascii':
        # in PY2 force encoding back to ascii
        return contents.encode('ascii', 'replace')
    else:
        # in all other cases, try to decode to target encoding
        try:
            return contents.decode(encoding, 'replace')
        except AttributeError:
            pass
    # if all else fails, just return the contents "as is"
    return contents


class FileMixin(object):
    """File assertions mixin."""

    def exists(self):
        """Asserts that val is a path and that it exists."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a path')
        if not os.path.exists(self.val):
            self._err('Expected <%s> to exist, but was not found.' % self.val)
        return self

    def does_not_exist(self):
        """Asserts that val is a path and that it does not exist."""
        if not isinstance(self.val, str_types):
            raise TypeError('val is not a path')
        if os.path.exists(self.val):
            self._err('Expected <%s> to not exist, but was found.' % self.val)
        return self

    def is_file(self):
        """Asserts that val is an existing path to a file."""
        self.exists()
        if not os.path.isfile(self.val):
            self._err('Expected <%s> to be a file, but was not.' % self.val)
        return self

    def is_directory(self):
        """Asserts that val is an existing path to a directory."""
        self.exists()
        if not os.path.isdir(self.val):
            self._err('Expected <%s> to be a directory, but was not.' % self.val)
        return self

    def is_named(self, filename):
        """Asserts that val is an existing path to a file and that file is named filename."""
        self.is_file()
        if not isinstance(filename, str_types):
            raise TypeError('given filename arg must be a path')
        val_filename = os.path.basename(os.path.abspath(self.val))
        if val_filename != filename:
            self._err('Expected filename <%s> to be equal to <%s>, but was not.' % (val_filename, filename))
        return self

    def is_child_of(self, parent):
        """Asserts that val is an existing path to a file and that file is a child of parent."""
        self.is_file()
        if not isinstance(parent, str_types):
            raise TypeError('given parent directory arg must be a path')
        val_abspath = os.path.abspath(self.val)
        parent_abspath = os.path.abspath(parent)
        if not val_abspath.startswith(parent_abspath):
            self._err('Expected file <%s> to be a child of <%s>, but was not.' % (val_abspath, parent_abspath))
        return self
