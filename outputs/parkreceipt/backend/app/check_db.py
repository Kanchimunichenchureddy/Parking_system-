"""Read-only connection and schema check: python -m app.check_db."""
import sys
from .config import ConfigurationError

def main():
    try:
        from .models import engine,Base
        from .database_check import check_database
        problem=check_database(engine,Base.metadata)
    except ConfigurationError as exc: problem=str(exc)
    if problem:
        print(problem,file=sys.stderr);return 1
    print('Database connection and required tables are ready.');return 0

if __name__=='__main__':sys.exit(main())
