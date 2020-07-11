# assertpy docs

Documentation is mostly written inline using Python docstrings that are in
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) format.
[Sphinx](https://www.sphinx-doc.org/) and the
[Napoleon extension](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html)
are used to generate html.

## Setup

Install `sphinx` via pip...

```
pip install sphinx
pip install sphinxcontrib-napoleon
```

And checkout the [assertpy.github.io](https://github.com/assertpy/assertpy.github.io)
repo as a sibling to `assertpy`.

```
cd ..
git clone git@github.com:assertpy/assertpy.github.io.git
```

## Build

To build the docs, run:

```
cd docs/
./build.sh
```

This generates `docs.html` and copies is directly into the sibling
`assertpy.github.io` repo.

