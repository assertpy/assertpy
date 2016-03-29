from distutils.core import setup
import assertpy

desc = """assertpy
========

Dead simple assertion library for python unit testing with a fluent API
that supports Python 2 and 3.

Usage
'''''

Just import the ``assert_that`` function, and away you go::

    from assertpy import assert_that

    def test_something():
        assert_that(1 + 2).is_equal_to(3)
        assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')
        assert_that(['a', 'b', 'c']).contains('a').does_not_contain('x')

Of course, ``assertpy`` works best with a python test runner
like `pytest <http://pytest.org/latest/contents.html>`_ (our favorite)
or `Nose <http://nose.readthedocs.org/>`_."""

setup(name = 'assertpy',
    packages = ['assertpy'],
    version = assertpy.__version__,
    description = 'Assertion library for python unit testing with a fluent API',
    long_description = desc,
    author = 'Justin Shacklette',
    author_email = 'justin@saturnboy.com',
    url = 'https://github.com/ActivisionGameScience/assertpy',
    download_url = 'https://codeload.github.com/ActivisionGameScience/assertpy/tar.gz/%s' % assertpy.__version__,
    keywords = ['test', 'testing', 'assert', 'assertion', 'assertthat', 'assert_that', 'nose', 'nosetests', 'pytest', 'unittest'],
    license = 'BSD',
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development',
        'Topic :: Software Development :: Testing'])
