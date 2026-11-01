"""assertpy2 is now assertpy: everything here is the object of the same name in `assertpy`."""

from assertpy import *  # noqa: F403 - the bridge re-exports the whole public surface under the old name
from assertpy import __all__ as __all__
