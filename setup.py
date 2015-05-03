from distutils.core import setup

import assertpy

readme = open('README.md').read()


setup(name = 'assertpy',
    packages = ['assertpy'],
    version = assertpy.__version__,
    description = 'Assertion framework for python unit testing with a fluent API',
    long_description = readme,
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
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Software Development',
        'Topic :: Software Development :: Testing']
)
