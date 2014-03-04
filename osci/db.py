import logging
import MySQLdb

from osci import test


class DB:
    log = logging.getLogger('citrix.db')
    def __init__(self, host, user, passwd):
        self.conn = None
        self.host = host
        self.user = user
        self.passwd = passwd
        self.connect()

    def create_database_and_schema(self, database):
        try:
            self.execute('USE %s'%database)
        except:
            self.execute('CREATE DATABASE %s'%database)
            self.execute('USE %s'%database)

        test.Test.createTable(self)

    def connect(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception, e:
                self.log.exception(e)
        self.conn = MySQLdb.connect(self.host, self.user, self.passwd)

    def execute(self, sql, retry=True):
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
            self.conn.commit()
        except (AttributeError, MySQLdb.OperationalError):
            if retry:
                self.connect()
                self.execute(sql, False)
        except:
            self.log.error('Error running SQL %s'%sql)
            self.conn.rollback()

    def query(self, sql, retry=True):
        cur = self.conn.cursor()
        try:
            cur.execute(sql)
            results = cur.fetchall()
            self.conn.commit()
            return results
        except (AttributeError, MySQLdb.OperationalError):
            if retry:
                self.connect()
                return self.query(sql, False)

