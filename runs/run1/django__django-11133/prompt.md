You are working in the Django repository at /testbed, checked out at the commit where the issue below was reported.

<issue>
HttpResponse doesn't handle memoryview objects
Description
	
I am trying to write a BinaryField retrieved from the database into a HttpResponse. When the database is Sqlite this works correctly, but Postgresql returns the contents of the field as a memoryview object and it seems like current Django doesn't like this combination:
from django.http import HttpResponse																	 
# String content
response = HttpResponse("My Content")																			
response.content																								 
# Out: b'My Content'
# This is correct
# Bytes content
response = HttpResponse(b"My Content")																		 
response.content																								 
# Out: b'My Content'
# This is also correct
# memoryview content
response = HttpResponse(memoryview(b"My Content"))															 
response.content
# Out: b'<memory at 0x7fcc47ab2648>'
# This is not correct, I am expecting b'My Content'
</issue>

Resolve the issue by editing the non-test source files in /testbed.

- Find the code involved, reproduce the problem if practical, then make a minimal, correct fix.
- Run the relevant existing tests to check your change, for example:
  `cd /testbed/tests && python runtests.py --settings=test_sqlite --parallel 1 <test_module>`
- Do not modify or add files under /testbed/tests. Your fix will be checked against hidden tests.
- Do not commit. When the fix is in place and the tests you ran pass, stop.
