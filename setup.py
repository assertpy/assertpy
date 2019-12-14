from distutils.core import setup
import assertpy

desc = """
assertpy
========

Simple assertions library for unit testing in Python with a nice fluent API. Supports both Python 2 and 3.

Usage
-----

Just import the ``assert_that`` function, and away you go...::

    from assertpy import assert_that

    def test_something():
        assert_that(1 + 2).is_equal_to(3)
        assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')
        assert_that(['a', 'b', 'c']).contains('a').does_not_contain('x')

Of course, assertpy works best with a python test runner like `pytest <http://pytest.org/>`_ (our favorite) or `Nose <http://nose.readthedocs.org/>`_.

Install
-------

The assertpy library is available via `PyPI <https://pypi.org/project/assertpy/>`_.
Just install with::

    pip install assertpy

Or, if you are a big fan of `conda <https://conda.io/>`_ like we are, there is an
`assertpy-feedstock <https://github.com/conda-forge/assertpy-feedstock>`_ for
`Conda-Forge <https://conda-forge.org/>`_ that you can use::

    conda install assertpy --channel conda-forge

"""

setup(
    name='assertpy',
    packages=['assertpy'],
    version=assertpy.__version__,
    description='Simple assertion library for unit testing in python with a fluent API',
    long_description=desc,
    author='Justin Shacklette',
    author_email='justin@saturnboy.com',
    url='https://github.com/assertpy/assertpy',
    download_url='https://github.com/assertpy/assertpy/archive/%s.tar.gz' % assertpy.__version__,
    keywords=['test', 'testing', 'assert', 'assertion', 'assertthat', 'assert_that', 'nose', 'nosetests', 'pytest', 'unittest'],
    license='BSD',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Software Development',
        'Topic :: Software Development :: Testing'])
