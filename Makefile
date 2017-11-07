testall:
	PYTHONPATH=./rwlock nosetests-2.7 tests/ -v -s -d --with-coverage --with-xunit --cover-erase

testall3:
	PYTHONPATH=./rwlock nosetests-3.4 tests/ -v -s -d --with-coverage --with-xunit --cover-erase
