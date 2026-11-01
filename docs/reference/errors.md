# Structured failures

The exception raised when an assertion fails, carrying the structured diff.

``AssertionFailure`` subclasses ``AssertionError``, so existing ``except AssertionError`` handlers keep
working unchanged. See [Errors & reporting](../guides/errors.md) for usage.

::: assertpy.errors.AssertionFailure
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.errors.DiffResult
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.errors.Step
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.errors.DiffEntry
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.errors.PollTrace
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.errors.PollSample
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.errors.DanglingAssertionWarning
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.errors.VacuousAssertionWarning
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true
