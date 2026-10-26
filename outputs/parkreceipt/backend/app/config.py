"""Explicit database configuration; never guess a database password."""
import os
from pathlib import Path
from sqlalchemy.engine import make_url

class ConfigurationError(RuntimeError): pass

def load_env_file(path: Path):
    """Read literal KEY=value lines. Existing process variables take precedence."""
    if not path.is_file(): return
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line=raw.strip()
        if not line or line.startswith('#'): continue
        if line.startswith('export '): line=line[7:]
        key,sep,value=line.partition('=')
        key=key.strip();value=value.strip()
        if not sep or not key.isidentifier():
            raise ConfigurationError(f'Invalid configuration line {number} in {path.name}. Use KEY=value.')
        if value[:1] in ('"',"'"):
            if len(value)<2 or value[-1]!=value[0]:
                raise ConfigurationError(f'Unclosed quoted value on line {number} in {path.name}.')
            value=value[1:-1]
        os.environ.setdefault(key,value)

BACKEND=Path(__file__).resolve().parents[1]
# Most specific file first, then project settings. Shell/Compose always wins.
load_env_file(BACKEND/'.env')
load_env_file(BACKEND.parent/'.env')

def database_url():
    value=os.getenv('DATABASE_URL','').strip()
    if not value:
        raise ConfigurationError('DATABASE_URL is missing. From backend run: python -m app.configure_db. For a separate SQLite rehearsal run: python3 start_local.py from the project folder. No default database credentials are used.')
    try: url=make_url(value)
    except Exception:
        raise ConfigurationError('DATABASE_URL is invalid. Run python -m app.configure_db to safely encode the database credentials.') from None
    if url.drivername not in ('mysql+pymysql','sqlite'):
        raise ConfigurationError('Use a mysql+pymysql:// URL for MySQL or sqlite:/// for an explicit local rehearsal.')
    if url.drivername=='mysql+pymysql' and (not url.username or not url.database):
        raise ConfigurationError('The MySQL URL needs a database username and database name.')
    return url
