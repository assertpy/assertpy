from distutils.core import setup
import assertpy

desc = """assertpy
========

Dead simple assertions framework for unit testing in Python with a nice fluent API.

Usage
'''''

Just import the ``assert_that`` function, and away you go::

    from assertpy import assert_that

    class TestSomething(object):
        def test_something(self):
            assert_that(1 + 2).is_equal_to(3)
            assert_that('foobar').is_length(6).starts_with('foo').ends_with('bar')

Of course, ``assertpy`` works best with a python test runner
like `Nose <http://nose.readthedocs.org/>`_
or `pytest <http://pytest.org/latest/contents.html>`_."""

setup(name = 'assertpy',
    packages = ['assertpy'],
    version = assertpy.__version__,
    description = 'Assertion framework for python unit testing with a fluent API',
    long_description = desc,
    author = 'Justin Shacklette',
    author_email = 'justin@saturnboy.com',
    url = 'https://github.com/ActivisionGameScience/assertpy',
    download_url = 'https://github.com/ActivisionGameScience/assertpy/archive/%s.tar.gz' % assertpy.__version__,
    keywords = ['testing', 'assert', 'assertion', 'assert_that'],
    license = 'BSD',
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development',
        'Topic :: Software Development :: Testing']
)
