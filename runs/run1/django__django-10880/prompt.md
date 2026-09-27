You are working in the Django repository at /testbed, checked out at the commit where the issue below was reported.

<issue>
Query syntax error with condition and distinct combination
Description
	
A Count annotation containing both a Case condition and a distinct=True param produces a query error on Django 2.2 (whatever the db backend). A space is missing at least (... COUNT(DISTINCTCASE WHEN ...).
</issue>

Resolve the issue by editing the non-test source files in /testbed.

- Find the code involved, reproduce the problem if practical, then make a minimal, correct fix.
- Run the relevant existing tests to check your change, for example:
  `cd /testbed/tests && python runtests.py --settings=test_sqlite --parallel 1 <test_module>`
- Do not modify or add files under /testbed/tests. Your fix will be checked against hidden tests.
- Do not commit. When the fix is in place and the tests you ran pass, stop.
