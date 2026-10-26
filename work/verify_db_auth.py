import os,sys,secrets,subprocess,tempfile,contextlib,io
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine,text
from sqlalchemy.engine import URL
root=Path.cwd()/'outputs/parkreceipt/backend'
sys.path.insert(0,str(root))
from app import configure_db
socket='/private/tmp/parkreceipt-isolated.sock'
admin=create_engine(URL.create('mysql+pymysql',username='root',database='parkreceipt_migration',query={'unix_socket':socket}))
user='probe_'+secrets.token_hex(5)
password=secrets.token_urlsafe(20)+'@:#%'
with admin.begin() as c:
 c.execute(text('CREATE USER :user@\'localhost\' IDENTIFIED BY :password'),{'user':user,'password':password})
 c.execute(text('GRANT SELECT ON parkreceipt_migration.* TO :user@\'localhost\''),{'user':user})
try:
 for secret,expected in [(password,0),('intentionally-wrong-password',1)]:
  url=URL.create('mysql+pymysql',username=user,password=secret,host='localhost',database='parkreceipt_migration',query={'unix_socket':socket})
  result=subprocess.run([sys.executable,'-m','app.check_db'],cwd=root,env={**os.environ,'DATABASE_URL':url.render_as_string(hide_password=False)},text=True,capture_output=True)
  assert result.returncode==expected,(result.stdout,result.stderr)
  assert password not in result.stdout+result.stderr and secret not in result.stdout+result.stderr
  if expected:assert '1045' in result.stderr
  print('Correct credentials: connection/schema check passed.' if not expected else 'Rejected credentials: exact MySQL 1045 reproduced; safe diagnostic returned.')
 with tempfile.TemporaryDirectory(dir=Path.cwd()/'work') as temp:
  base=Path(temp);(base/'app').mkdir()
  output=io.StringIO()
  with patch.object(configure_db,'__file__',str(base/'app/configure_db.py')),patch('builtins.input',side_effect=['localhost','3306',user,'parkreceipt_migration',socket]),patch('getpass.getpass',return_value=password),contextlib.redirect_stdout(output):
   assert configure_db.main()==0
  contents=(base/'.env').read_text()
  assert '%40' in contents and password not in contents
  assert (base/'.env').stat().st_mode&0o777==0o600
  print('Private configuration helper: verified login, encoded special characters, saved mode 0600 in disposable folder.')
finally:
 with admin.begin() as c:c.execute(text('DROP USER :user@\'localhost\''),{'user':user})
 admin.dispose()
