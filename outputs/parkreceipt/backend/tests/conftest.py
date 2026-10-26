import os
import tempfile
_workspace=tempfile.TemporaryDirectory(prefix='parkreceipt-tests-')
os.environ['DATABASE_URL']=os.getenv('TEST_DATABASE_URL','sqlite:///'+_workspace.name+'/test.db')
os.environ['APP_ORIGIN']='http://testserver'
