import os
# Set before any test imports app.db/settings. Integration fixtures only clear
# dedicated database names beginning router_test.
if os.environ.get('TEST_DATABASE_URL'):
    os.environ['DATABASE_URL']=os.environ['TEST_DATABASE_URL']
