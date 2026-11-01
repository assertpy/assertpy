# assertpy2 is now assertpy

This library took over the `assertpy` name with version 2.35.0. From that version on, `assertpy2` installs `assertpy` 2.x and hands out the same objects under the old name, so existing code keeps running.

Switch when convenient:

```diff
- assertpy2
+ assertpy
```

```diff
- from assertpy2 import assert_that
+ from assertpy import assert_that
```

The pytest flags, settings and environment variables that carried the `2` keep working through 2.x with a `FutureWarning`. See [Coming from assertpy2](https://assertpy.github.io/assertpy/getting-started/migration/#coming-from-assertpy2).
