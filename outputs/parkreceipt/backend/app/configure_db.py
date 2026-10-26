"""Prompt privately for existing MySQL credentials; verify before saving them."""
import getpass
import os
import tempfile
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from .database_check import database_problem

def main():
    print('Configure an existing MySQL account. This does not create users, change passwords, or delete data.')
    host=input('MySQL host [127.0.0.1]: ').strip() or '127.0.0.1'
    port=int(input('Port [3306]: ').strip() or '3306')
    user=input('Database username [parkreceipt]: ').strip() or 'parkreceipt'
    password=getpass.getpass('Database password (not your website login): ')
    name=input('Database name [parkreceipt]: ').strip() or 'parkreceipt'
    socket=input('Unix socket path [leave blank for TCP]: ').strip()
    url=URL.create('mysql+pymysql',username=user,password=password,host=host,port=port,database=name,query={"unix_socket":socket} if socket else {})
    engine=create_engine(url,connect_args={'connect_timeout':5})
    try:
        with engine.connect() as c:c.execute(text('SELECT 1'))
    except SQLAlchemyError as exc:
        print(database_problem(exc));return 1
    finally:engine.dispose()
    path=Path(__file__).resolve().parents[1]/'.env'
    lines=path.read_text().splitlines() if path.exists() else []
    lines=[line for line in lines if line.strip().removeprefix('export ').partition('=')[0].strip()!='DATABASE_URL']
    lines.append('DATABASE_URL='+url.render_as_string(hide_password=False))
    fd,temporary=tempfile.mkstemp(prefix='.env-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:f.write('\n'.join(lines)+'\n')
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    print('Connection succeeded. Saved backend/.env with owner-only permissions. No database contents were changed.')
    print('If DATABASE_URL is exported in this terminal, unset it to use this file. Next: python -m app.check_db')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,KeyboardInterrupt,EOFError):raise SystemExit('Setup cancelled or invalid input; no credentials saved.')
