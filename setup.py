from distutils.core import setup
from pip.req import parse_requirements
from pip.download import PipSession

import assertpy

readme = open('README.md').read()


session = PipSession()
requirements = [
    str(req.req) for req in parse_requirements('requirements.txt', session=session)
]

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
    install_requires=requirements,
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
