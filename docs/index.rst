assertpy
^^^^^^^^

Simple assertions library for unit testing in Python with a nice fluent API.  Supports both Python 2 and 3.

Usage
=====

Just import the ``assert_that`` function, and away you go...::

    from assertpy import assert_that

    def test_something():
        assert_that(1 + 2).is_equal_to(3)
        assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')
        assert_that(['a', 'b', 'c']).contains('a').does_not_contain('x')

Of course, assertpy works best with a python test runner like `pytest <http://pytest.org/>`_ (our favorite) or `Nose <http://nose.readthedocs.org/>`_.

Installation
============

Install with pip
----------------

The assertpy library is available via `PyPI <https://pypi.org/project/assertpy/>`_.
Just install with::

    pip install assertpy

Install with conda
------------------

Or, if you are a big fan of `conda <https://conda.io/>`_ like we are, there is an
`assertpy-feedstock <https://github.com/conda-forge/assertpy-feedstock>`_ for
`Conda-Forge <https://conda-forge.org/>`_ that you can use::

    conda install assertpy --channel conda-forge

API
=====

.. toctree::
    :maxdepth: 3

    assertpy

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
