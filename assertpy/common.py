import collections
import sys

if sys.version_info[0] == 3:
    str_types = (str,)
    xrange = range
    unicode = str
else:
    str_types = (basestring,)
    xrange = xrange
    unicode = unicode


def is_dict_like(value):
    return (isinstance(value, collections.Iterable) and
            hasattr(value, 'keys') and
            callable(getattr(value, 'keys')) and
            hasattr(value, '__getitem__'))


def assert_is_dict_like(value, identifier='val'):
    if not is_dict_like(value):
        raise TypeError('{} is not dict-like'.format(identifier))
