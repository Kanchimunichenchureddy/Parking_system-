import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from app.config import ConfigurationError,database_url,load_env_file
from app.database_check import database_problem,check_database
from app.models import Base
from app.main import app

def test_missing_url_has_no_placeholder_fallback(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with pytest.raises(ConfigurationError,match='DATABASE_URL is missing'):database_url()

def test_env_loading_preserves_shell_settings(tmp_path,monkeypatch):
    monkeypatch.setenv('DATABASE_URL','sqlite:///existing.db')
    monkeypatch.delenv('PARK_TEST_OPTION',raising=False)
    env=tmp_path/'.env';env.write_text('# settings\nDATABASE_URL=mysql+pymysql://ignored:secret@localhost/db\nPARK_TEST_OPTION="value"\n')
    load_env_file(env)
    assert os.environ['DATABASE_URL']=='sqlite:///existing.db'
    assert os.environ['PARK_TEST_OPTION']=='value'

def test_diagnostics_redact_credentials_and_sql():
    exc=OperationalError('SELECT secret_token',{'password':'DO_NOT_LEAK'},Exception(1045,'secret database password'))
    message=database_problem(exc)
    assert '1045' in message and 'database login rejected' in message
    assert 'DO_NOT_LEAK' not in message and 'secret_token' not in message

def test_schema_check_distinguishes_missing_tables():
    engine=create_engine('sqlite://')
    assert 'tables are missing' in check_database(engine,Base.metadata)
    Base.metadata.create_all(engine)
    assert check_database(engine,Base.metadata) is None
    engine.dispose()

def test_missing_cookie_returns_401_without_database_call():
    with patch('sqlalchemy.orm.Session.get',side_effect=AssertionError('No database call expected')):
        assert TestClient(app).get('/api/me').status_code==401

def test_runtime_outage_returns_safe_503():
    exc=OperationalError('sensitive SQL',{},Exception(1045,'DO_NOT_LEAK'))
    with patch('sqlalchemy.orm.Session.get',side_effect=exc):
        c=TestClient(app);c.cookies.set('session','unknown-token')
        r=c.get('/api/me')
    assert r.status_code==503 and 'Payment outcome is unknown' in r.json()['detail']
    assert 'DO_NOT_LEAK' not in r.text and r.headers['Retry-After']=='5'

def test_startup_checks_database_before_serving():
    with patch('app.main.check_database',return_value='MySQL 1045: database login rejected.'):
        with pytest.raises(RuntimeError,match='MySQL 1045'):
            with TestClient(app):pass
