# coding: utf-8
import time, datetime, os
import types, random
import threading
import logging
import copy
import traceback
from zbase3.base import pager
from contextlib import contextmanager
log = logging.getLogger()

dbpool = None

_trans_func = {}

def timeit(func):
    def _(*args, **kwargs):
        starttm = time.time()
        ret = 0
        num = 0
        err = ''
        try:
            retval = func(*args, **kwargs)
            if isinstance(retval, list):
                num = len(retval)
            elif isinstance(retval, dict):
                num = 1
            elif isinstance(retval, int):
                ret = retval
            return retval
        except Exception as e:
            err = e
            ret = -1
            raise
        finally:
            endtm = time.time()
            conn = args[0]
            #dbcf = conn.pool.dbcf
            dbcf = conn.param
            log.info('server=%s|id=%d|name=%s|user=%s|r=%s|addr=%s:%d|db=%s|c=%d,%d,%d|tr=%d|time=%d|ret=%s|n=%d|sql=%s|err=%s',
                     conn.type, conn.conn_id%10000,
                     conn.name, dbcf.get('user',''), conn.role,
                     dbcf.get('host',''), dbcf.get('port',0),
                     dbcf.get('db',''),
                     len(conn.pool.dbconn_idle),
                     len(conn.pool.dbconn_using),
                     conn.pool.max_conn, conn.trans,
                     int((endtm-starttm)*1000000),
                     str(ret), num,
                     repr(args[1]), err)
    return _


class DBPoolBase:
    def acquire(self, name):
        pass

    def release(self, name, conn):
        pass


class DBResult:
    def __init__(self, fields, data):
        self.fields = fields
        self.data = data

    def todict(self):
        ret = []
        for item in self.data:
            ret.append(dict(zip(self.fields, item)))
        return ret

    def __iter__(self):
        for row in self.data:
            yield dict(zip(self.fields, row))

    def row(self, i, isdict=True):
        if isdict:
            return dict(zip(self.fields, self.data[i]))
        return self.data[i]

    def __getitem__(self, i):
        return dict(zip(self.fields, self.data[i]))

class DBFunc:
    def __init__(self, data):
        self.value = data


class DBConnection:
    def __init__(self, param, lasttime, status):
        self.name       = param.get('name')
        self.param      = param
        self.conn       = None
        self.status     = status
        self.lasttime   = lasttime
        self.pool       = None
        self.server_id  = None
        self.conn_id    = 0
        self.trans      = 0 # is start transaction
        self.role       = param.get('role', 'm') # master/slave

    def __str__(self):
        return '<%s %s:%d %s@%s>' % (self.type,
                self.param.get('host',''), self.param.get('port',0),
                self.param.get('user',''), self.param.get('db',0)
                )

    def is_available(self):
        return self.status == 0

    def useit(self):
        self.status = 1
        self.lasttime = time.time()

    def releaseit(self):
        self.status = 0

    def connect(self):
        pass

    def close(self):
        pass

    def alive(self):
        pass

    def cursor(self):
        return self.conn.cursor()

    @timeit
    def execute(self, sql, param=None):
        #log.info('exec:%s', sql)
        cur = self.conn.cursor()
        if param:
            ret = cur.execute(sql, param)
        else:
            ret = cur.execute(sql)
        cur.close()
        return ret

    @timeit
    def executemany(self, sql, param=None):
        cur = self.conn.cursor()
        ret = cur.executemany(sql, param)
        cur.close()
        return ret

    @timeit
    def query(self, sql, param=None, isdict=True, head=False):
        '''sql查询，返回查询结果'''
        #log.info('query:%s', sql)
        cur = self.conn.cursor()
        if param:
            cur.execute(sql, param)
        else:
            cur.execute(sql)
        res = cur.fetchall()
        cur.close()
        res = [self.format_timestamp(r, cur) for r in res]
        #log.info('desc:', cur.description)
        global _trans_func
        if res and isdict:
            ret = []
            xkeys = [ i[0] for i in cur.description]
            for item in res:
                one = dict(zip(xkeys, item))
                if _trans_func:
                    for k in xkeys:
                        if k in _trans_func:
                            one[k] = _trans_func[k](k, one[k])
                ret.append(one)
        else:
            ret = res
            if head:
                xkeys = [ i[0] for i in cur.description]
                ret.insert(0, xkeys)
        return ret

    @timeit
    def get(self, sql, param=None, isdict=True):
        '''sql查询，只返回一条'''
        cur = self.conn.cursor()
        cur.execute(sql, param)
        res = cur.fetchone()
        cur.close()
        res = self.format_timestamp(res, cur)
        global _trans_func
        if res and isdict:
            xkeys = [ i[0] for i in cur.description]
            one = dict(zip(xkeys, res))
            
            if _trans_func:
                for k in xkeys:
                    if k in _trans_func:
                        one[k] = _trans_func[k](k, one[k])
            return one
        else:
            return res

    def value2sql(self, v, charset='utf-8'):
        if isinstance(v, str):
            if v.startswith(('now()','md5(')):
                return v
            return "'%s'" % self.escape(v)
        elif isinstance(v, datetime.datetime) or isinstance(v, datetime.date):
            return "'%s'" % str(v)
        elif isinstance(v, DBFunc):
            return v.value
        elif isinstance(v, bytes):
            return v.decode(charset)
        else:
            if v is None:
                return 'NULL'
            return str(v)

    def exp2sql(self, key, op, value):
        item = '(`%s` %s ' % (key.strip('`').replace('.','`.`'), op)
        if op == 'in':
            item += '(%s))' % ','.join([self.value2sql(x) for x in value])
        elif op == 'not in':
            item += '(%s))' % ','.join([self.value2sql(x) for x in value])
        elif op == 'between':
            item += ' %s and %s)' % (self.value2sql(value[0]), self.value2sql(value[1]))
        else:
            item += self.value2sql(value) + ')'
        return item

    def dict2sql(self, d, sp=','):
        '''字典可以是 {name:value} 形式，也可以是 {name:(operator, value)}'''
        x = []
        for k,v in d.items():
            if isinstance(v, tuple):
                x.append('%s' % self.exp2sql(k, v[0], v[1]))
            else:
                x.append('`%s`=%s' % (k.strip(' `').replace('.','`.`'), self.value2sql(v)))
        return sp.join(x)

    def dict2on(self, d, sp=' and '):
        x = []
        for k,v in d.items():
            x.append('`%s`=`%s`' % (k.strip(' `').replace('.','`.`'), v.strip(' `').replace('.','`.`')))
        return sp.join(x)

    def dict2insert(self, d):
        keys = list(d.keys())
        keys.sort()
        vals = []
        for k in keys:
            vals.append('%s' % self.value2sql(d[k]))
        new_keys = ['`' + k.strip('`') + '`' for k in keys]
        return ','.join(new_keys), ','.join(vals)

    def fields2where(self, fields, where=None):
        if not where:
            where = {}
        for f in fields:
            if f.value == None or (f.value == '' and f.must):
                continue
            where[f.name] = (f.op, f.value)
        return where

    def format_table(self, table):
        '''调整table 支持加上 `` 并支持as'''
        #如果有as
        table = table.strip(' `').replace(',','`,`')
        index = table.find(' ')
        if ' ' in table:
            return '`%s`%s' % ( table[:index] ,table[index:])
        else:
            return '`%s`' % table

    def insert(self, table, values, other=None):
        #sql = "insert into %s set %s" % (table, self.dict2sql(values))
        keys, vals = self.dict2insert(values)
        sql = "insert into %s(%s) values (%s)" % (self.format_table(table), keys, vals)
        if other:
            sql += ' ' + other
        return self.execute(sql)

    def insert_list(self, table, values_list, other=None):
        sql = 'insert into %s ' % self.format_table(table)
        sql_key = ''
        sql_value = []
        for values in values_list:
            keys, vals = self.dict2insert(values)
            sql_key = keys  # 正常key肯定是一样的
            sql_value.append('(%s)' % vals)
        sql += ' (' + sql_key + ') ' + 'values' + ','.join(sql_value)
        if other:
            sql += ' ' + other
        return self.execute(sql)

    def update(self, table, values, where=None, other=None):
        sql = "update %s set %s" % (self.format_table(table), self.dict2sql(values))
        if where:
            sql += " where %s" % self.dict2sql(where,' and ')
        if other:
            sql += ' ' + other
        return self.execute(sql)

    def delete(self, table, where, other=None):
        sql = "delete from %s" % self.format_table(table)
        if where:
            sql += " where %s" % self.dict2sql(where, ' and ')
        if other:
            sql += ' ' + other
        return self.execute(sql)

    def select(self, table, where=None, fields='*', other=None, isdict=True):
        sql = self.select_sql(table, where, fields, other)
        return self.query(sql, None, isdict=isdict)

    def select_one(self, table, where=None, fields='*', other=None, isdict=True):
        if not other:
            other = ' limit 1'
        if 'limit' not in other:
            other += ' limit 1'

        sql = self.select_sql(table, where, fields, other)
        return self.get(sql, None, isdict=isdict)

    def select_join(self, table1, table2, join_type='inner', on=None, where=None, fields='*', other=None, isdict=True):
        sql = self.select_join_sql(table1, table2, join_type, on, where, fields, other)
        return self.query(sql, None, isdict=isdict)

    def select_join_one(self, table1, table2, join_type='inner', on=None, where=None, fields='*', other=None, isdict=True):
        if not other:
            other = ' limit 1'
        if 'limit' not in other:
            other += ' limit 1'

        sql = self.select_join_sql(table1, table2, join_type, on, where, fields, other)
        return self.get(sql, None, isdict=isdict)

    def select_sql(self, table, where=None, fields='*', other=None):
        #if type(fields) in (types.ListType, types.TupleType):
        if isinstance(fields, (list, tuple)):
            fields = ','.join(fields)
        sql = "select %s from %s" % (fields, self.format_table(table))
        if where:
            sql += " where %s" % self.dict2sql(where, ' and ')
        if other:
            sql += ' ' + other
        return sql

    def select_join_sql(self, table1, table2, join_type='inner', on=None, where=None, fields='*', other=None):
        #if type(fields) in (types.ListType, types.TupleType):
        if isinstance(fields, (list, tuple)):
            fields = ','.join(fields)
        sql = "select %s from %s %s join %s" % (fields, self.format_table(table1), join_type, self.format_table(table2))
        if on:
            sql += " on %s" % self.dict2on(on, ' and ')
        if where:
            sql += " where %s" % self.dict2sql(where, ' and ')
        if other:
            sql += ' ' + other
        return sql

    def select_page(self, sql, pagecur=1, pagesize=20, count_sql=None, maxid=-1):
        return pager.db_pager(self, sql, pagecur, pagesize, count_sql, maxid)

    def last_insert_id(self):
        pass

    def start(self): # start transaction
        self.trans = 1
        pass

    def commit(self):
        self.trans = 0
        self.conn.commit()

    def rollback(self):
        self.trans = 0
        self.conn.rollback()

    def escape(self, s):
        return s

    def format_timestamp(self, ret, cur):
        '''将字段以_time结尾的格式化成datetime'''
        if not ret:
            return ret
        index = []
        for d in cur.description:
            if d[0].endswith('_time'):
                index.append(cur.description.index(d))

        res = []
        for i , t in enumerate(ret):
            #if i in index and type(t) in [types.IntType,types.LongType]:
            if i in index and isinstance(t, int):
                res.append(datetime.datetime.fromtimestamp(t))
            else:
                res.append(t)
        return res

def with_mysql_reconnect(func):

    def close_mysql_conn(self):
        try:
            self.conn.close()
        except:
            log.warning(traceback.format_exc())
            self.conn = None

    def _(self, *args, **argitems):
        if self.type == 'mysql':
            import MySQLdb as m
        elif self.type == 'pymysql':
            import pymysql as m
        trycount = 3
        while True:
            try:
                x = func(self, *args, **argitems)
            except m.OperationalError as e:
                log.warning(traceback.format_exc())
                if e.args[0] >= 2000 and self.trans == 0: # 客户端错误
                    close_mysql_conn(self)
                    self.connect()
                    trycount -= 1
                    if trycount > 0:
                        continue
                raise
            except (m.InterfaceError, m.InternalError):
                log.warning(traceback.format_exc())
                if self.trans == 0:
                    close_mysql_conn(self)
                    self.connect()
                    trycount -= 1
                    if trycount > 0:
                        continue
                raise
            else:
                return x
    return _


class MySQLConnection (DBConnection):
    type = "mysql"
    def __init__(self, param, lasttime, status):
        DBConnection.__init__(self, param, lasttime, status)

        self.connect()

    def useit(self):
        self.status = 1
        self.lasttime = time.time()

    def releaseit(self):
        self.status = 0

    def connect(self):
        engine = self.param['engine']
        if engine == 'mysql':
            import MySQLdb
            self.conn = MySQLdb.connect(host = self.param['host'],
                                        port = self.param['port'],
                                        user = self.param['user'],
                                        passwd = self.param['passwd'],
                                        db = self.param['db'],
                                        charset = self.param['charset'],
                                        connect_timeout = self.param.get('timeout', 10),
                                        )

            self.conn.autocommit(1)

            cur = self.conn.cursor()
            cur.execute("show variables like 'server_id'")
            row = cur.fetchone()
            self.server_id = int(row[1])
            cur.close()

            cur = self.conn.cursor()
            cur.execute("select connection_id()")
            row = cur.fetchone()
            self.conn_id = row[0]
            cur.close()


            #if self.param.get('autocommit',None):
            #    log.note('set autocommit')
            #    self.conn.autocommit(1)
            #initsqls = self.param.get('init_command')
            #if initsqls:
            #    log.note('init sqls:', initsqls)
            #    cur = self.conn.cursor()
            #    cur.execute(initsqls)
            #    cur.close()
        else:
            raise ValueError('engine error:' + engine)
        log.info('server=%s|func=connect|id=%d|name=%s|user=%s|role=%s|addr=%s:%d|db=%s',
                    self.type, self.conn_id%10000,
                    self.name, self.param.get('user',''), self.role,
                    self.param.get('host',''), self.param.get('port',0),
                    self.param.get('db',''))

    def close(self):
        log.info('server=%s|func=close|id=%d', self.type, self.conn_id%10000)
        self.conn.close()
        self.conn = None

    @with_mysql_reconnect
    def alive(self):
        if self.is_available():
            cur = self.conn.cursor()
            cur.execute("show tables;")
            cur.close()
            self.conn.ping()

    @with_mysql_reconnect
    def execute(self, sql, param=None):
        return DBConnection.execute(self, sql, param)

    @with_mysql_reconnect
    def executemany(self, sql, param):
        return DBConnection.executemany(self, sql, param)

    @with_mysql_reconnect
    def query(self, sql, param=None, isdict=True, head=False):
        return DBConnection.query(self, sql, param, isdict, head)

    @with_mysql_reconnect
    def get(self, sql, param=None, isdict=True):
        return DBConnection.get(self, sql, param, isdict)

    def escape(self, s, enc='utf-8'):
        #if type(s) == types.UnicodeType:
        #    s = s.encode(enc)
        ns = self.conn.escape_string(s)
        #return unicode(ns, enc)
        return ns

    def last_insert_id(self):
        ret = self.query('select last_insert_id()', isdict=False)
        return ret[0][0]

    def start(self):
        self.trans = 1
        sql = "start transaction"
        return self.execute(sql)

    def commit(self):
        self.trans = 0
        sql = 'commit'
        return self.execute(sql)

    def rollback(self):
        self.trans = 0
        sql = 'rollback'
        return self.execute(sql)

class PyMySQLConnection (MySQLConnection):
    type = "pymysql"
    def __init__(self, param, lasttime, status):
        MySQLConnection.__init__(self, param, lasttime, status)

    def connect(self):
        engine = self.param['engine']
        if engine == 'pymysql':
            import pymysql
            self.conn = pymysql.connect(host = self.param['host'],
                                        port = self.param['port'],
                                        user = self.param['user'],
                                        passwd = self.param['passwd'],
                                        db = self.param['db'],
                                        charset = self.param['charset'],
                                        connect_timeout = self.param.get('timeout', 10),
                                        )
            self.conn.autocommit(1)
            self.trans = 0

            cur = self.conn.cursor()
            cur.execute("show variables like 'server_id'")
            row = cur.fetchone()
            self.server_id = int(row[1])
            cur.close()

            cur = self.conn.cursor()
            cur.execute("select connection_id()")
            row = cur.fetchone()
            self.conn_id = row[0]
            cur.close()

        else:
            raise ValueError('engine error:' + engine)
        log.info('server=%s|func=connect|id=%d|name=%s|user=%s|role=%s|addr=%s:%d|db=%s',
                    self.type, self.conn_id%10000,
                    self.name, self.param.get('user',''), self.role,
                    self.param.get('host',''), self.param.get('port',0),
                    self.param.get('db',''))

class SQLiteConnection (DBConnection):
    type = "sqlite"
    def __init__(self, param, lasttime, status):
        DBConnection.__init__(self, param, lasttime, status)

    def connect(self):
        engine = self.param['engine']
        self.trans = 0
        if engine == 'sqlite':
            import sqlite3
            self.conn = sqlite3.connect(self.param['db'], detect_types=sqlite3.PARSE_DECLTYPES, isolation_level=None)
        else:
            raise ValueError('engine error:' + engine)

    def useit(self):
        DBConnection.useit(self)
        if not self.conn:
            self.connect()

    def releaseit(self):
        DBConnection.releaseit(self)
        self.conn.close()
        self.conn = None

    def escape(self, s, enc='utf-8'):
        s = s.replace("'", "\'")
        s = s.replace('"', '\"')
        return s

    def last_insert_id(self):
        ret = self.query('select last_insert_rowid()', isdict=False)
        return ret[0][0]

    def start(self):
        self.trans = 1
        sql = "BEGIN"
        return self.conn.execute(sql)



class DBPool (DBPoolBase):
    def __init__(self, dbcf):
        # one item: [conn, last_get_time, stauts]
        self.dbconn_idle  = []
        self.dbconn_using = []

        self.dbcf   = dbcf
        self.max_conn = 20
        self.min_conn = 1

        #if self.dbcf.has_key('conn'):
        if 'conn' in self.dbcf:
            self.max_conn = self.dbcf['conn']

        self.connection_class = {}
        x = globals()
        for v in x.values():
            #if type(v) == types.ClassType and v != DBConnection and issubclass(v, DBConnection):
            if isinstance(v, type) and v != DBConnection and issubclass(v, DBConnection):
                self.connection_class[v.type] = v

        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)

        self.open(self.min_conn)

    def synchronize(func):
        def _(self, *args, **argitems):
            self.lock.acquire()
            x = None
            try:
                x = func(self, *args, **argitems)
            finally:
                self.lock.release()
            return x
        return _

    def open(self, n=1):
        param = self.dbcf
        newconns = []
        for i in range(0, n):
            myconn = self.connection_class[param['engine']](param, time.time(), 0)
            myconn.pool = self
            newconns.append(myconn)
        self.dbconn_idle += newconns

    def clear_timeout(self):
        #log.info('try clear timeout conn ...')
        now = time.time()
        dels = []
        allconn = len(self.dbconn_idle) + len(self.dbconn_using)
        for c in self.dbconn_idle:
            if allconn == 1:
                break
            if now - c.lasttime > self.dbcf.get('idle_timeout', 10):
                dels.append(c)
                allconn -= 1

        if dels:
            log.debug('close timeout db conn:%d', len(dels))
        for c in dels:
            if c.conn:
                c.close()
            self.dbconn_idle.remove(c)

    @synchronize
    def acquire(self, timeout=10):
        start = time.time()
        while len(self.dbconn_idle) == 0:
            if len(self.dbconn_idle) + len(self.dbconn_using) < self.max_conn:
                self.open()
                continue
            self.cond.wait(timeout)
            if int(time.time() - start) > timeout:
                log.error('func=acquire|error=no idle connections')
                raise RuntimeError('no idle connections')

        conn = self.dbconn_idle.pop(0)
        conn.useit()
        self.dbconn_using.append(conn)

        if random.randint(0, 100) > 80:
            try:
                self.clear_timeout()
            except:
                log.error(traceback.format_exc())

        return conn

    @synchronize
    def release(self, conn):
        if conn:
            if conn.trans:
                log.debug('realse close conn use transaction')
                conn.close()
                #conn.connect()

            self.dbconn_using.remove(conn)
            conn.releaseit()
            if conn.conn:
                self.dbconn_idle.insert(0, conn)
        self.cond.notify()


    @synchronize
    def alive(self):
        for conn in self.dbconn_idle:
            conn.alive()

    def size(self):
        return len(self.dbconn_idle), len(self.dbconn_using)


class DBConnProxy:
    #def __init__(self, masterconn, slaveconn):
    def __init__(self, pool, timeout=10):
        #self.name   = ''
        #self.master = masterconn
        #self.slave  = slaveconn

        self._pool = pool
        self._master = None
        self._slave = None
        self._timeout = timeout

        self._modify_methods = set(['execute', 'executemany', 'last_insert_id',
                'insert', 'update', 'delete', 'insert_list', 'start', 'rollback', 'commit'])

    def __getattr__(self, name):
        #if name.startswith('_') and name[1] != '_':
        #    return self.__dict__[name]
        if name in self._modify_methods:
            if not self._master:
                self._master = self._pool.master.acquire(self._timeout)
            return getattr(self._master, name)
        else:
            if name == 'master':
                if not self._master:
                    self._master = self._pool.master.acquire(self._timeout)
                return self._master
            if name == 'slave':
                if not self._slave:
                    self._slave = self._pool.get_slave().acquire(self._timeout)
                return self._slave

            if not self._slave:
                self._slave = self._pool.get_slave().acquire(self._timeout)
            return getattr(self._slave, name)


class RWDBPool:
    def __init__(self, dbcf):
        self.dbcf   = dbcf
        self.name   = ''
        self.policy = dbcf.get('policy', 'round_robin')

        master_cf = dbcf.get('master', None)
        master_cf['name'] = dbcf.get('name', '')
        master_cf['role'] = 'm'
        self.master = DBPool(master_cf)

        self.slaves = []

        self._slave_current = -1

        for x in dbcf.get('slave', []):
            x['name'] = dbcf.get('name', '')
            x['role'] = 's'
            slave = DBPool(x)
            self.slaves.append(slave)

    def get_slave(self):
        if self.policy == 'round_robin':
            size = len(self.slaves)
            self._slave_current = (self._slave_current + 1) % size
            return self.slaves[self._slave_current]
        else:
            raise ValueError('policy not support')

    def get_master(self):
        return self.master

#    def acquire(self, timeout=10):
#        #log.debug('rwdbpool acquire')
#        master_conn = None
#        slave_conn  = None
#
#        try:
#            master_conn = self.master.acquire(timeout)
#            slave_conn  = self.get_slave().acquire(timeout)
#            return DBConnProxy(master_conn, slave_conn)
#        except:
#            if master_conn:
#                master_conn.pool.release(master_conn)
#            if slave_conn:
#                slave_conn.pool.release(slave_conn)
#            raise

    def acquire(self, timeout=10):
        return DBConnProxy(self, timeout)

    def release(self, conn):
        #log.debug('rwdbpool release')
        if conn._master:
            #log.debug('release master')
            conn._master.pool.release(conn._master)
        if conn._slave:
            #log.debug('release slave')
            conn._slave.pool.release(conn._slave)


    def size(self):
        ret = {'master': (-1,-1), 'slave':[]}
        if self.master:
            x = self.master
            key = '%s@%s:%d' % (x.dbcf['user'], x.dbcf['host'], x.dbcf['port'])
            ret['master'] = (key, self.master.size())
        for x in self.slaves:
            key = '%s@%s:%d' % (x.dbcf['user'], x.dbcf['host'], x.dbcf['port'])
            ret['slave'].append((key, x.size()))
        return ret




def checkalive(name=None):
    global dbpool
    while True:
        if name is None:
            checknames = dbpool.keys()
        else:
            checknames = [name]
        for k in checknames:
            pool = dbpool[k]
            pool.alive()
        time.sleep(300)

def install(cf):
    global dbpool
    if dbpool:
        log.warn("too many install db")
        return dbpool
    dbpool = {}

    for name,item in cf.items():
        item['name']  = name
        dbp = None
        if 'master' in item:
            dbp = RWDBPool(item)
        else:
            dbp = DBPool(item)
        dbpool[name] = dbp
    return dbpool


def acquire(name, timeout=10):
    global dbpool
    #log.info("acquire:", name)
    pool = dbpool[name]
    x = pool.acquire(timeout)
    x.name = name
    return x

def release(conn):
    if not conn:
        return
    global dbpool
    #log.info("release:", name)
    pool = dbpool[conn.name]
    return pool.release(conn)

def execute(db, sql, param=None):
    return db.execute(sql, param)

def executemany(db, sql, param):
    return db.executemany(sql, param)

def query(db, sql, param=None, isdict=True, head=False):
    return db.query(sql, param, isdict, head)


def add_trans(key, func):
    global _trans_func
    if isinstance(key, list):
        for k in key:
            _trans_func[k] = func
    else:
        _trans_func[key] = func



# 推荐使用的获取数据库连接的方法
@contextmanager
def get_connection(token):
    conn = None
    try:
        conn = acquire(token)
        yield conn
    except:
        log.error("error=%s", traceback.format_exc())
        raise
    finally:
        if conn:
            release(conn)

get_connection_exception = get_connection

@contextmanager
def get_connection_noexcept(token):
    conn = None
    try:
        conn = acquire(token)
        yield conn
    except:
        log.error("error=%s", traceback.format_exc())
    finally:
        if conn:
            release(conn)


# 只能用在类方法上面，并且并不推荐使用此方法，使用get_connection更好
def with_database(name, errfunc=None, errstr=''):
    def f(func):
        def _(self, *args, **argitems):
            self.db = acquire(name)
            x = None
            try:
                x = func(self, *args, **argitems)
            except:
                if errfunc:
                    return getattr(self, errfunc)(error=errstr)
                else:
                    raise
            finally:
                release(self.db)
            return x
        return _
    return f

def test_sqlite():
    import random
    dbcf = {'test1': {'engine': 'sqlite', 'db':'test1.db', 'conn':1}}
    #dbcf = {'test1': {'engine': 'sqlite', 'db':':memory:', 'conn':1}}
    if os.path.isfile('test1.db'):
        os.remove('test1.db')
    install(dbcf)

    with get_connection('test1') as conn:
        sql = "create table if not exists user(id integer primary key, name varchar(32), ctime timestamp)"
        conn.execute(sql)

        sql1 = "insert into user values (%d, 'zhaowei', datetime())" % (random.randint(1, 100));
        conn.execute(sql1)

        conn.insert("user", {"name":"bobo","ctime":DBFunc("datetime()")})

        sql2 = "select * from user"
        ret = conn.query(sql2)
        log.debug('result:%s', ret)

        ret = conn.query('select * from user where name=?', ('bobo',))
        log.debug('result:%s', ret)


    class Test2:
        @with_database("test1")
        def test2(self):
            ret = self.db.query("select * from user")
            log.debug(ret)

    log.debug('-' * 60)
    t = Test2()
    t.test2()


def test_ms_3():
    for i in range(0, 10):
        n = random.randint(1, 10)
        conns = []

        last = dbpool['test'].size()

        log.warn('acquire ... %d', n)
        for i in range(0, n):
            c = acquire('test')
            conns.append(c)
            c.execute('create table if not exists ztest(id int(4) not null primary key auto_increment, name varchar(128) not null)')
            c.insert('ztest', {'name':'zhaowei%d'%(i)})

            c.query('select count(*) from ztest')
            c.get('select count(*) from ztest')
            c.select('ztest', fields='count(*)')

            x = dbpool['test'].size()
            
            last = x


        log.warn('release ... %d', n)
        for c in conns:
            release(c)
            #print(dbpool['test'].size())

        print('-'*60)
        print(dbpool['test'].size())
        time.sleep(1)

def test4(tcount):
    def run_thread():
        while True:
            time.sleep(0.01)
            conn = None
            try:
                conn = acquire('test')
            except:
                log.debug("%s catch exception in acquire", threading.currentThread().name)
                traceback.print_exc()
                time.sleep(0.5)
                continue
            try:
                sql = "select count(*) from profile"
                ret = conn.query(sql)
            except:
                log.debug("%s catch exception in query", threading.currentThread().name)
                traceback.print_exc()
            finally:
                if conn:
                    release(conn)
                    conn = None

    import threading
    th = []
    for i in range(0, tcount):
        _th = threading.Thread(target=run_thread, args=())
        log.debug("%s create", _th.name)
        th.append(_th)

    for t in th:
        t.start()
        log.debug("%s start", t.name)

    for t in th:
        t.join()
        log.debug("%s finish",t.name)


def test5():
    def run_thread():
        i = 0
        while i < 10:
            time.sleep(0.01)
            with get_connection('test') as conn:
                sql = "select count(*) from profile"
                ret = conn.query(sql)
                log.debug('ret:%s', ret)
            i += 1
        pool = dbpool['test']
        log.debug("pool size: %s", pool.size())

    import threading
    th = []
    for i in range(0, 10):
        _th = threading.Thread(target=run_thread, args=())
        log.debug("%s create", _th.name)
        th.append(_th)

    for t in th:
        t.setDaemon(True)
        t.start()
        log.debug("%s start", t.name)

def test_format_time():
    with get_connection('test') as conn:
        print(conn.select('order'))
        print(conn.select_join('app','customer','inner',))
        print(conn.format_table('order as o'))

def test_base_func():
    with get_connection('test') as conn:
        conn.insert('auth_user',{
            'username':'13512345677',
            'password':'123',
            'mobile':'13512345677',
            'email':'123@test.cn',
        })
        print( conn.select('auth_user',{
            'username':'13512345677',
        }))
        conn.delete('auth_user',{
            'username':'13512345677',
        })
        conn.select_join('profile as p','auth_user as a',where={
            'p.userid':DBFunc('a.id'),
        })

def test_new_rw():
    import logger
    logger.install('stdout')
    database = {'test':{
                'policy': 'round_robin',
                'default_conn':'auto',
                'master':
                    {'engine':'pymysql',
                     'db':'test',
                     'host':'172.100.101.156',
                     'port':3306,
                     'user':'qf',
                     'passwd':'123456',
                     'charset':'utf8',
                     'conn':10}
                 ,
                 'slave':[
                    {'engine':'pymysql',
                     'db':'test',
                     'host':'172.100.101.156',
                     'port':3306,
                     'user':'qf',
                     'passwd':'123456',
                     'charset':'utf8',
                     'conn':10
                    },
                    {'engine':'pymysql',
                     'db':'test',
                     'host':'172.100.101.156',
                     'port':3306,
                     'user':'qf',
                     'passwd':'123456',
                     'charset':'utf8',
                     'conn':10
                    }

                 ]
             }
            }
    install(database)

    def printt(t=0):
        now = time.time()
        if t > 0:
            print('time:', now-t)
        return now

    t = printt()
    with get_connection('test') as conn:
        t = printt(t)
        print('master:', conn._master, 'slave:', conn._slave)
        assert conn._master == None
        assert conn._slave == None
        ret = conn.query("select 10")
        t = printt(t)
        print('after read master:', conn._master, 'slave:', conn._slave)
        assert conn._master == None
        assert conn._slave != None
        conn.execute('create table if not exists haha (id int(4) not null primary key, name varchar(128) not null)')
        t = printt(t)
        print('master:', conn._master, 'slave:', conn._slave)
        assert conn._master != None
        assert conn._slave != None
        conn.execute('drop table haha')
        t = printt(t)
        assert conn._master != None
        assert conn._slave != None
        print('ok')

    print('=' * 20)
    t = printt()
    with get_connection('test') as conn:
        t = printt(t)
        print('master:', conn._master, 'slave:', conn._slave)
        assert conn._master == None
        assert conn._slave == None

        ret = conn.master.query("select 10")
        assert conn._master != None
        assert conn._slave == None

        t = printt(t)
        print('after query master:', conn._master, 'slave:', conn._slave)
        ret = conn.query("select 10")
        assert conn._master != None
        assert conn._slave != None

        print('after query master:', conn._master, 'slave:', conn._slave)
        print('ok')

def test_trans():
    with get_connection('test') as conn:
        conn.start()
        conn.select_one('order')
        conn.get('select connection_id()')

        conn.select_one('order')

    with get_connection('test') as conn:
        conn.select_one('order')
        conn.get('select connection_id()')


def test_init_db(way='simple'):
    import copy

    DB = {'engine':'pymysql',   # db type, eg: mysql, sqlite
          'db':'test',        # db name
          'host':'127.0.0.1', # db host
          'port':3306,        # db port
          'user':'root',      # db user
          'passwd':'123456',  # db password
          'charset':'utf8',   # db charset
          'conn':10}          # db connections in pool

    DATABASE = {'test':
        copy.deepcopy(DB)
    }

    DB1 = copy.deepcopy(DB)
    DB2 = copy.deepcopy(DB)
    DB3 = copy.deepcopy(DB)
    DB4 = copy.deepcopy(DB)

    DB2['user'] = 'testr1'
    DB3['user'] = 'testr2'
    DB4['user'] = 'testr3'

    if way != 'simple':
        DATABASE = {
        'test':{
            'policy': 'round_robin',
            'default_conn':'auto',
            'master': DB1,
            'slave':[DB2, DB3, DB4],
            },
        }

    install(DATABASE)


def test_main():
    import logger
    logger.install('stdout')
    
    #test_sqlite()

    test_init_db('auto')
    test_ms_3()

    #test_with()
    #test5()
    #time.sleep(50)
    #pool = dbpool['test']
    #test3()
    #test4()
    #test()
    #test_base_func()
    #test_new_rw()
    #test_db_install()
    #test_trans()
    print('complete!')



if __name__ == '__main__':
    test_main()

