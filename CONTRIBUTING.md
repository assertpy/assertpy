# Contributing

Any contributions of docs or tests or code would be awesome.

Here's how:

1. Fork it
1. Clone your fork (`git clone https://my_fork`)
1. Create a branch (`git checkout -b my_branch`)
1. Commit your changes (`git commit -am "added some cool feature"`)
1. Push to the branch to your fork (`git push origin my_branch`)
1. Open a [Pull Request](http://github.com/ActivisionGameScience/assertpy/pulls)
1. Respond to any questions during our review process

Read more about how pulls work on GitHub's [Using Pull Requests](https://help.github.com/articles/using-pull-requests/) page.

## Running the Tests

Before even thinking about sending us a pull request, you must first write some tests (and
eat some dogfood by using `assertpy` assertions in any tests you write).

Our favorite python test runner is [pytest](http://pytest.org/). To run all the
tests, just execute `py.test` in the base project folder (above the `tests/` folder)
like this:

```
PYTHONPATH=. py.test -v tests
```

Should produce output something like this:

```
===== test session starts =====
collected 373 items

tests/test_bool.py::TestBool::test_is_true PASSED
..
tests/test_type.py::TestType::test_is_instance_of_bad_arg_failure PASSED

===== 373 passed in 0.52 seconds =====
```
