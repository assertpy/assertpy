"""assertpy2 is now assertpy: everything here is the object of the same name in `assertpy`."""

from assertpy import *  # noqa: F403 - the bridge re-exports the whole public surface under the old name
from assertpy import __all__ as __all__
from assertpy2 import assertpy as assertpy
from assertpy2 import async_assertions as async_assertions
from assertpy2 import base as base
from assertpy2 import bytes_mixin as bytes_mixin
from assertpy2 import collection as collection
from assertpy2 import contains as contains
from assertpy2 import dataframe as dataframe
from assertpy2 import date as date
from assertpy2 import dict as dict  # noqa: A004 - the submodule 2.34 had, bound where it was
from assertpy2 import dynamic as dynamic
from assertpy2 import errors as errors
from assertpy2 import exception as exception
from assertpy2 import extracting as extracting
from assertpy2 import file as file
from assertpy2 import helpers as helpers
from assertpy2 import http_mixin as http_mixin
from assertpy2 import json_mixin as json_mixin
from assertpy2 import matchers as matchers
from assertpy2 import numeric as numeric
from assertpy2 import outcome as outcome
from assertpy2 import snapshot as snapshot
from assertpy2 import string as string
from assertpy2 import warning as warning
