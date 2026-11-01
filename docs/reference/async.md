# Async & eventual assertions

Poll a callable until an assertion passes or the timeout expires. Start with ``eventually()`` on a
callable value, chain the assertion you expect to eventually hold, and await the result. Use
``eventually_sync()`` for the same polling without an event loop. See
[Testing](../guides/testing.md#async-assertions) for usage.

::: assertpy.assertpy.AssertionBuilder.eventually
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.assertpy.AssertionBuilder.eventually_sync
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.async_assertions.AsyncAssertionBuilder
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true

::: assertpy.async_assertions.SyncAssertionBuilder
    options:
      show_root_heading: true
      show_root_full_path: false
      show_root_toc_entry: true
