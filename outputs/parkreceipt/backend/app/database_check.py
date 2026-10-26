"""Database diagnostics that never print passwords, SQL parameters or connection URLs."""
from sqlalchemy import inspect,text
from sqlalchemy.exc import SQLAlchemyError

def database_problem(exc):
    original=getattr(exc,'orig',exc)
    args=getattr(original,'args',())
    code=args[0] if args and isinstance(args[0],int) else None
    if code==1045:
        return 'MySQL 1045: database login rejected. Check the database username, password and matching MySQL user/host account. Website owner/staff passwords are unrelated. Run python -m app.configure_db with valid database credentials.'
    if code==1044:
        return 'MySQL 1044: the database account cannot access the selected database. Ask its administrator to grant access to that database.'
    if code==1049:
        return 'MySQL 1049: the selected database does not exist. Ask its administrator to create it or choose the correct database name.'
    if code in (2002,2003,2005,2006,2013):
        return 'MySQL connection unavailable. Check that MySQL is running and verify the configured host, port or socket. The hostname db works inside Compose, not in a normal host terminal.'
    return 'Database unavailable or incompatible with the application schema. Run python -m app.check_db and verify DATABASE_URL; apply migrations with alembic upgrade head when the connection works.'

def check_database(engine,metadata):
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            missing=set(metadata.tables)-set(inspect(connection).get_table_names())
            if missing:
                return 'Database connection succeeded, but application tables are missing: '+', '.join(sorted(missing))+'. From backend run: alembic upgrade head, then python -m app.seed.'
    except SQLAlchemyError as exc:
        return database_problem(exc)
    return None
