You are working in the Django repository at /testbed, checked out at the commit where the issue below was reported.

<issue>
Add DISTINCT support for Avg and Sum aggregates.
Description
	
As an extension of #28658, aggregates should be supported for other general aggregates such as Avg and Sum. Before 2.2, these aggregations just ignored the parameter, but now throw an exception.
This change would just involve setting these classes as allowing DISTINCT, and could also be applied to Min and Max (although pointless).
</issue>

Resolve the issue by editing the non-test source files in /testbed.

- Find the code involved, reproduce the problem if practical, then make a minimal, correct fix.
- Run the relevant existing tests to check your change, for example:
  `cd /testbed/tests && python runtests.py --settings=test_sqlite --parallel 1 <test_module>`
- Do not modify or add files under /testbed/tests. Your fix will be checked against hidden tests.
- Do not commit. When the fix is in place and the tests you ran pass, stop.
