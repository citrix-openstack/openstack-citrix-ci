import logging
import contextlib
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# Import these, so that other modules can import it from here
from sqlalchemy import Column, Integer, String, DateTime, Text, UniqueConstraint
from sqlalchemy.exc import IntegrityError

from sqlalchemy import and_, or_

Base = declarative_base()


class DB(object):
    log = logging.getLogger('citrix.db')

    def __init__(self, database_url):
        self.database_url = database_url
        self.engine = create_engine(self.database_url)
        self.conn = None
        self.Session = scoped_session(sessionmaker(bind=self.engine))

    @contextlib.contextmanager
    def get_session(self):
        session = self.Session()
        yield session
        session.commit()

    def create_schema(self):
        Base.metadata.create_all(self.engine)
