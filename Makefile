testall:
	PYTHONPATH=./rwlock nosetests-2.7 tests/ -v -s -d --with-xunit --with-xcover --cover-erase
