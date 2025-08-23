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
import logging

from assertpy import assert_that, assert_warn, fail, WarningLoggingAdapter

if sys.version_info[0] == 3:
    from io import StringIO
else:
    from StringIO import StringIO


def test_success():
    assert_warn('foo').is_length(3)
    assert_warn('foo').is_not_empty()
    assert_warn('foo').is_true()
    assert_warn('foo').is_alpha()
    assert_warn('123').is_digit()
    assert_warn('foo').is_lower()
    assert_warn('FOO').is_upper()
    assert_warn('foo').is_equal_to('foo')
    assert_warn('foo').is_not_equal_to('bar')
    assert_warn('foo').is_equal_to_ignoring_case('FOO')


def test_failures():
    # capture log
    capture = StringIO()
    logger = logging.getLogger('capture')
    handler = logging.StreamHandler(capture)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn('foo', logger=adapted).is_length(4)
    assert_warn('foo', logger=adapted).is_empty()
    assert_warn('foo', logger=adapted).is_false()
    assert_warn('foo', logger=adapted).is_digit()
    assert_warn('123', logger=adapted).is_alpha()
    assert_warn('foo', logger=adapted).is_upper()
    assert_warn('FOO', logger=adapted).is_lower()
    assert_warn('foo', logger=adapted).is_equal_to('bar')
    assert_warn('foo', logger=adapted).is_not_equal_to('foo')
    assert_warn('foo', logger=adapted).is_equal_to_ignoring_case('BAR')

    # dump log to string
    out = capture.getvalue()
    capture.close()

    assert_that(out).contains('[test_warn.py:61]: Expected <foo> to be of length <4>, but was <3>.')
    assert_that(out).contains('[test_warn.py:62]: Expected <foo> to be empty string, but was not.')
    assert_that(out).contains('[test_warn.py:63]: Expected <foo> to be <False>, but was not.')
    assert_that(out).contains('[test_warn.py:64]: Expected <foo> to contain only digits, but did not.')
    assert_that(out).contains('[test_warn.py:65]: Expected <123> to contain only alphabetic chars, but did not.')
    assert_that(out).contains('[test_warn.py:66]: Expected <foo> to contain only uppercase chars, but did not.')
    assert_that(out).contains('[test_warn.py:67]: Expected <FOO> to contain only lowercase chars, but did not.')
    assert_that(out).contains('[test_warn.py:68]: Expected <foo> to be equal to <bar>, but was not.')
    assert_that(out).contains('[test_warn.py:69]: Expected <foo> to be not equal to <foo>, but was.')
    assert_that(out).contains('[test_warn.py:70]: Expected <foo> to be case-insensitive equal to <BAR>, but was not.')


def test_chained_failure():
    # capture log
    capture2 = StringIO()
    logger = logging.getLogger('capture2')
    handler = logging.StreamHandler(capture2)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    assert_warn('foo', logger=adapted).is_length(4).is_in('bar').does_not_contain_duplicates()

    # dump log to string
    out = capture2.getvalue()
    capture2.close()

    assert_that(out).contains('[test_warn.py:96]: Expected <foo> to be of length <4>, but was <3>.')
    assert_that(out).contains('[test_warn.py:96]: Expected <foo> to be in <bar>, but was not.')
    assert_that(out).contains('[test_warn.py:96]: Expected <foo> to not contain duplicates, but did.')


def test_failures_with_renamed_import():
    from assertpy import assert_warn as warn

    # capture log
    capture3 = StringIO()
    logger = logging.getLogger('capture3')
    handler = logging.StreamHandler(capture3)
    logger.addHandler(handler)
    adapted = WarningLoggingAdapter(logger, None)

    warn('foo', logger=adapted).is_length(4)
    warn('foo', logger=adapted).is_empty()
    warn('foo', logger=adapted).is_false()
    warn('foo', logger=adapted).is_digit()
    warn('123', logger=adapted).is_alpha()
    warn('foo', logger=adapted).is_upper()
    warn('FOO', logger=adapted).is_lower()
    warn('foo', logger=adapted).is_equal_to('bar')
    warn('foo', logger=adapted).is_not_equal_to('foo')
    warn('foo', logger=adapted).is_equal_to_ignoring_case('BAR')

    # dump log to string
    out = capture3.getvalue()
    capture3.close()

    assert_that(out).contains('[test_warn.py:117]: Expected <foo> to be of length <4>, but was <3>.')
    assert_that(out).contains('[test_warn.py:118]: Expected <foo> to be empty string, but was not.')
    assert_that(out).contains('[test_warn.py:119]: Expected <foo> to be <False>, but was not.')
    assert_that(out).contains('[test_warn.py:120]: Expected <foo> to contain only digits, but did not.')
    assert_that(out).contains('[test_warn.py:121]: Expected <123> to contain only alphabetic chars, but did not.')
    assert_that(out).contains('[test_warn.py:122]: Expected <foo> to contain only uppercase chars, but did not.')
    assert_that(out).contains('[test_warn.py:123]: Expected <FOO> to contain only lowercase chars, but did not.')
    assert_that(out).contains('[test_warn.py:124]: Expected <foo> to be equal to <bar>, but was not.')
    assert_that(out).contains('[test_warn.py:125]: Expected <foo> to be not equal to <foo>, but was.')
    assert_that(out).contains('[test_warn.py:126]: Expected <foo> to be case-insensitive equal to <BAR>, but was not.')
