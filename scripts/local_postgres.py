import subprocess
from pathlib import Path

root=Path('.local/postgres').resolve()
root.parent.mkdir(exist_ok=True)
pg=Path('C:/Program Files/PostgreSQL/18/bin')
if not (root/'PG_VERSION').exists():
    subprocess.run([str(pg/'initdb.exe'),'-D',str(root),'-U','router','-A','trust','--encoding=UTF8','--locale=C'],check=True)
if subprocess.run([str(pg/'pg_ctl.exe'),'-D',str(root),'status'],capture_output=True).returncode != 0:
    subprocess.run([str(pg/'pg_ctl.exe'),'-D',str(root),'-l',str(root.parent/'postgres.log'),'-o','-p 55432 -h 127.0.0.1','start'],check=True)
existing=subprocess.run([str(pg/'psql.exe'),'-h','127.0.0.1','-p','55432','-U','router','-d','postgres','-tAc',"SELECT 1 FROM pg_database WHERE datname='router'"],capture_output=True,text=True,check=True)
if existing.stdout.strip() != '1':
    subprocess.run([str(pg/'createdb.exe'),'-h','127.0.0.1','-p','55432','-U','router','router'],check=True)
