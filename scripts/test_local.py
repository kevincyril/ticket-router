from pathlib import Path
import os
import subprocess
from dotenv import load_dotenv
load_dotenv()
url=os.environ['DATABASE_URL']
base=url.rsplit('/',1)[0]
import psycopg
with psycopg.connect(base.replace('postgresql+psycopg','postgresql')+'/postgres',autocommit=True) as connection:
    if not connection.execute("SELECT 1 FROM pg_database WHERE datname='router_test'").fetchone():
        connection.execute('CREATE DATABASE router_test')
os.environ['TEST_DATABASE_URL']=base+'/router_test'
os.environ['DATABASE_URL']=os.environ['TEST_DATABASE_URL']
# Explicitly reset only the dedicated fixture database, then exercise migrations.
with psycopg.connect((base+'/router_test').replace('postgresql+psycopg','postgresql'),autocommit=True) as connection:
    assert connection.execute('SELECT current_database()').fetchone()[0]=='router_test'
    connection.execute('DROP TABLE IF EXISTS reviews, tickets, alembic_version CASCADE')
subprocess.run([str(Path('.venv/Scripts/python.exe')),'-m','alembic','upgrade','head'],check=True)
# Isolate Redis fixtures from application jobs.
os.environ['REDIS_URL']=os.environ['REDIS_URL'].rsplit('/',1)[0]+'/15'
raise SystemExit(subprocess.call([str(Path('.venv/Scripts/python.exe')),'-m','pytest','-m','not browser','-q']))
