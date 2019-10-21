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

"""Assertion library for python unit testing with a fluent API"""

import os
import contextlib
from .base import BaseMixin
from .contains import ContainsMixin
from .numeric import NumericMixin
from .string import StringMixin
from .collection import CollectionMixin
from .dict import DictMixin
from .date import DateMixin
from .file import FileMixin
from .extracting import ExtractingMixin
from .snapshot import SnapshotMixin
from .exception import ExceptionMixin
from .dynamic import DynamicMixin
from .helpers import HelpersMixin

__version__ = '0.14'

__tracebackhide__ = True # clean tracebacks via py.test integration
contextlib.__tracebackhide__ = True # monkey patch contextlib with clean py.test tracebacks


### soft assertions ###
_soft_ctx = 0
_soft_err = []

@contextlib.contextmanager
def soft_assertions():
    global _soft_ctx
    global _soft_err

    # init ctx
    if _soft_ctx == 0:
        _soft_err = []
    _soft_ctx += 1

    try:
        yield
    finally:
        # reset ctx
        _soft_ctx -= 1

    if _soft_err and _soft_ctx == 0:
        out = 'soft assertion failures:'
        for i,msg in enumerate(_soft_err):
            out += '\n%d. %s' % (i+1, msg)
        # reset msg, then raise
        _soft_err = []
        raise AssertionError(out)


### factory methods ###
def assert_that(val, description=''):
    """Factory method for the assertion builder with value to be tested and optional description."""
    global _soft_ctx
    if _soft_ctx:
        return AssertionBuilder(val, description, 'soft')
    return AssertionBuilder(val, description)

def assert_warn(val, description=''):
    """Factory method for the assertion builder with value to be tested, optional description, and
       just warn on assertion failures instead of raisings exceptions."""
    return AssertionBuilder(val, description, 'warn')

def fail(msg=''):
    """Force test failure with the given message."""
    raise AssertionError('Fail: %s!' % msg if msg else 'Fail!')

def soft_fail(msg=''):
    """Adds error message to soft errors list if within soft assertions context.
       Either just force test failure with the given message."""
    global _soft_ctx
    if _soft_ctx:
        global _soft_err
        _soft_err.append('Fail: %s!' % msg if msg else 'Fail!')
        return
    fail(msg)


class AssertionBuilder(DynamicMixin, ExceptionMixin, SnapshotMixin, ExtractingMixin,
        FileMixin, DateMixin, DictMixin, CollectionMixin, StringMixin, NumericMixin,
        ContainsMixin, HelpersMixin, BaseMixin, object):
    """Assertion builder."""

    def __init__(self, val, description='', kind=None, expected=None):
        """Construct the assertion builder."""
        self.val = val
        self.description = description
        if kind not in set([None, 'soft', 'warn']):
            raise ValueError('bad assertion kind')
        self.kind = kind
        self.expected = expected

    def _builder(self, val, description='', kind=None, expected=None):
        """Helper to build a new Builder. Only used when we don't want to chain."""
        return AssertionBuilder(val, description, kind, expected)

    def _err(self, msg):
        """Helper to raise an AssertionError, and optionally prepend custom description."""
        out = '%s%s' % ('[%s] ' % self.description if len(self.description) > 0 else '', msg)
        if self.kind == 'warn':
            print(out)
            return self
        elif self.kind == 'soft':
            global _soft_err
            _soft_err.append(out)
            return self
        else:
            raise AssertionError(out)
