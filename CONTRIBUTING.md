# Contributing

Any contributions of docs or tests or code would be awesome.

Here's how:

1. Fork it
1. Create a branch (`git checkout -b my_branch`)
1. Commit your changes (`git commit -am "added some cool feature"`)
1. Push to the branch (`git push origin my_branch`)
1. Open a [Pull Request](http://github.com/ActivisionGameScience/assertpy/pulls)
1. Respond to any questions during our review process

Read more about how pulls work on GitHub's [Using Pull Requests](https://help.github.com/articles/using-pull-requests/) page.

## Running the Tests

Before even thinking about sending us a pull request, you must first write some tests (and
eat some dogfood by using `assertpy` assertions in any tests you write).

Our favorite python test runner is [Nose](https://nose.readthedocs.org/). To run all the
tests, just execute `nosetests` in the base project folder (above the `tests/` folder)
like this:

```
nosetests
```

Should produce output something like this:

```
....
------------------------
Ran 5000 tests in 0.024s
```

Nose is a powerful test runner, if you want all the details read the [docs](https://nose.readthedocs.org/).
One very useful hint...if you want to run the tests in a single file, just append the path
to that file to the `nosetests` command.  For example, run the
tests in `test_equals.py` file in the `tests` folder like this:

```
nosetests tests/test_equals.py
```
