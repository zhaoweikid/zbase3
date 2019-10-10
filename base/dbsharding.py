# coding: utf-8
'''
CREATE DATABASE dbmeta;
CREATE TABLE instance (
    id bigint(20) not null primary key,
    name varchar(128) not null COMMENT '数据库实例名称',
    host varchar(128) not null COMMENT '数据库地址 ip',
    port smallint not null COMMENT '数据库实例服务端口',
    dbgroup varchar(128) not null COMMENT '数据库组，或者说是集群名称',
    dbtype varchar(64) not null COMMENT '数据库类型: master/slave/master_proxy/slave_proxy/proxy',
    master varchar(128) COMMENT '该实例的master的name',
    ctime DATETIME not null COMMENT '添加时间',
    utime DATETIME not null COMMENT '更新时间'
)ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT '数据库实例表';

CREATE TABLE logic_db (
    id bigint(20) not null primary key,
    name varchar(128) not null COMMENT '逻辑库名',
    policy varchar(256) COMMENT '库拆分策略, {"db":["db1","db2"],"default":"db1","rule":[["^aa|bb|cc$","db1"],["func:fname","db1"]]}',
    ctime DATETIME not null COMMENT '添加时间',
    utime DATETIME not null COMMENT '更新时间'
)ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT '数据库分库';

CREATE TABLE logic_table (
    id bigint(20) not null primary key,
    dbname varchar(128) not null COMMENT '逻辑库名',
    tbname varchar(128) not null COMMENT '逻辑表名',
    way varchar(16) not null default 'r' COMMENT '表拆分的方式: r(横向拆分)/c(纵向拆分)',
    policy varchar(64) not null COMMENT '横向拆分策略: hash/month/day',
    field varchar(64) default 'id' COMMENT '拆分策略的字段名，默认为id'
    memo varchar(1024) COMMENT '扩展信息，横向拆分策略:{"count":10},纵向拆分策略{"table":["t1","t2"],["f1,f2","t1"],["f3,f4","t2"]}',
    ctime DATETIME not null COMMENT '添加时间',
    utime DATETIME not null COMMENT '更新时间'
)ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT '数据库分表';
'''
import time, datetime, os
import types, random
import threading
import logging
import copy
import json
import re
import traceback
from zbase3.base import pager, dbpool
from contextlib import contextmanager
log = logging.getLogger()

class ShardingError (Exception):
    pass

class ShardingConnProxy:
    def __init__(self, manager, name):
        self._mg = manager
        self._name = name
        self._info = manager._dbinfo.get(name)
        self._conn = {}
        self._last_conn = None

    def _route(self, table):
        '''根据表名返回对应的数据库名'''
        if not self._info:
            return None

        dbs = self._info.get('db')
        if not dbs:
            log.info('not found policy:db')
            return None

        rule = self._info.get('rule')
        if not rule:
            log.info('not found policy:rule')
            return None

        default = self._info.get('default')
        if not default:
            log.info('not found policy:default')
            return None

        for r,db in rule:
            #log.debug('%s: %s', r, db)
            if r.startswith('var:'):
                r1 = r[4:]
                tx = table.split('_')
                rx = r1.split('_')

                if tx[0] != rx[0]:
                    #log.debug('prefix not equal: %s', tx[0])
                    continue


                now = datetime.datetime.now()
                month = '%d%02d' % (now.year, now.month)

                tv1 = int(tx[1])
                mv1 = int(month)
                #log.debug('%d %d r1:%s', tv1, mv1, r1)
                if r1.find('month_last1') >= 0:
                    if mv1 == tv1:
                        return db
                elif r1.find('month_last2') >= 0:
                    if mv1 - tv1 <= 1:
                        return db
                elif r1.find('month_last3') >= 0:
                    if mv1 - tv1 <= 2:
                        return db
                elif r1.find('month') >= 0:
                    return db

            elif r[0] == '^' and re.match(r, table):
                return db
            else:
                p = r.split(',')
                if table in p:
                    return db


        return default

    def _get_conn(self, tname):
        '''根据表名返回数据库连接对象'''
        log.debug('get conn: %s', tname)

        dbnm = self._route(tname)

        if not dbnm: # 无数据表映射到库，所以使用默认的库
            dbnm = self._name

        # 真实数据库名转换到数据库配置的key名称
        tb = self._mg._dbname.get(dbnm, dbnm)
        if tb in self._conn:
            log.debug('get conn %s in cache', tb)
            conn = self._conn[tb]
        else: 
            conn = dbpool.acquire(tb)
            self._conn[tb] = conn
        self._last_conn = conn

        return conn

    def _get_table(self, sql):
        '''从sql语句中分析出表名，只支持简单查询'''
        # NOTE: 仅能支持只对一个表进行简单的查询
        p = sql.lower().split()
        idx = p.index('from')
        if idx < 0:
            raise ValueError('not found table')
        tb = p[idx+1]
        return tb


    def release(self):
        for name,conn in self._conn.items():
            try:
                log.debug('release %s', name)
                dbpool.release(conn)
            except:
                log.warn(traceback.format_exc())
        self._conn = {}
        self._last_conn = None


    def insert(self, table, values, other=None):
        conn = self._get_conn(table)
        return conn.insert(table, values, other)


    def insert_list(self, table, values_list, other=None):
        conn = self._get_conn(table)
        return conn.insert_list(table, values_list, other) 

    def last_insert_id(self):
        if self._last_conn:
            self._last_conn.last_insert_id()

    def update(self, table, values, where=None, other=None):
        conn = self._get_conn(table)
        return conn.update(table, values, where, other)


    def select(self, table, where=None, fields='*', other=None, isdict=True):
        conn = self._get_conn(table)
        return conn.select(table, where, fields, other, isdict) 


    def select_one(self, table, where=None, fields='*', other=None, isdict=True):
        conn = self._get_conn(table)
        return conn.select_one(table, where, fields, other, isdict)


    def select_sql(self, table, where=None, fields='*', other=None):
        conn = self._get_conn(table)
        return conn.select_sql(table, where, fields, other)


    def select_page(self, sql, pagecur=1, pagesize=20, count_sql=None, maxid=-1):
        conn = self._get_conn(table)
        return conn.select_page(sql, pagecur, pagesize, count_sql, maxid)

    def delete(self, table, where, other=None):
        conn = self._get_conn(table)
        return conn.delete(table, where, other)

    def query(self, sql, param=None, isdict=True, head=False):
        table = self._get_table(sql)
        conn = self._get_conn(table)
        return conn.query(sql, param, isdict, head)

    def get(self, sql, param=None, isdict=True):
        table = self._get_table(sql)
        conn = self._get_conn(table)
        return conn.get(sql, param, isdict)

    def execute(self, sql, param=None):
        table = self._get_table(sql)
        conn = self._get_conn(table)
        return conn.execute(sql, param)

    def executemany(self, sql, param=None):
        table = self._get_table(sql)
        conn = self._get_conn(table)
        return conn.executemany(sql, param)

    def start(self):
        raise ShardingError("not support transaction")

    def commit(self):
        raise ShardingError("not support transaction")

    def rollback(self):
        raise ShardingError("not support transaction")



class ShardingManager:
    def __init__(self):
        self._dbinfo = {}
        self._dbname = {}
        
        #self.load()
    
    def load(self):
        if self._dbname:
            return

        with dbpool.get_connection('dbmeta') as conn:
            ret = conn.select('logic_db')
            if ret:
                for row in ret:
                    log.debug(row['policy'])
                    self._dbinfo[row['name']] = json.loads(row['policy'])

        # 真实数据库名和该库的配置KEY的映射
        for name,pool in dbpool.dbpool.items():
            log.debug('%s => %s', pool.dbcf['db'], name)
            self._dbname[pool.dbcf['db']] = name


sharding = None

def install():
    global sharding
    sharding = ShardingManager()
    sharding.load()


@contextmanager
def get_connection(name):
    global sharding
    try:
        conn = ShardingConnProxy(sharding, name)
        yield conn
    except:
        log.error("error=%s", traceback.format_exc())
        raise
    finally:
        if conn:
            conn.release()



def test():
    import pprint, copy

    DB = {
        'engine':'pymysql',   # db type, eg: mysql, sqlite
        'db':'test',        # db name
        'host':'127.0.0.1', # db host
        'port':3306,        # db port
        'user':'root',      # db user
        'passwd':'123456',  # db password
        'charset':'utf8',   # db charset
        'conn':3,
    }

    DB1 = copy.copy(DB)
    DB1['db'] = 'test1'

    DB2 = copy.copy(DB)
    DB2['db'] = 'test2'

    DATABASE = {
        'dbmeta': {
            'engine':'pymysql',
            'db':'dbmeta',
            'host':'127.0.0.1',
            'port':3306,
            'user':'root',
            'passwd':'123456',
            'charset':'utf8',
            'conn':3,
        },
        'test':DB,
        'test-1': DB1,
        'test-2': DB2,
    }

    dbpool.install(DATABASE)
    install()

    sqls = {
        'test':[
            "DROP TABLE testme;",
            "CREATE TABLE IF NOT EXISTS testme(" \
              "id int(4) not null primary key auto_increment, " \
              "name varchar(128), ctime int(4));",
            "CREATE TABLE IF NOT EXISTS record_201908(" \
              "id int(4) not null primary key auto_increment, " \
              "amt int(4) not null default 0);",
            "CREATE TABLE IF NOT EXISTS record_201907(" \
              "id int(4) not null primary key auto_increment, " \
              "amt int(4) not null default 0);",
            "CREATE TABLE IF NOT EXISTS record_201906(" \
              "id int(4) not null primary key auto_increment, " \
              "amt int(4) not null default 0);",
        ],

        'test-1':[
            "DROP TABLE testme1;",
            "CREATE TABLE IF NOT EXISTS testme1(" \
              "id int(4) not null primary key auto_increment, " \
              "name varchar(128), ctime int(4));",

            "CREATE TABLE IF NOT EXISTS record_201905(" \
              "id int(4) not null primary key auto_increment, " \
              "amt int(4) not null default 0);",
            "CREATE TABLE IF NOT EXISTS record_201904(" \
              "id int(4) not null primary key auto_increment, " \
              "amt int(4) not null default 0);",
            "CREATE TABLE IF NOT EXISTS record_201903(" \
              "id int(4) not null primary key auto_increment, " \
              "amt int(4) not null default 0);",
            "CREATE TABLE IF NOT EXISTS record_201902(" \
              "id int(4) not null primary key auto_increment, " \
              "amt int(4) not null default 0);",

        ],
        
        'test-2':[
            "DROP TABLE testme2;",
            "CREATE TABLE IF NOT EXISTS testme2(" \
              "id int(4) not null primary key auto_increment, " \
              "name varchar(128), ctime int(4));",
            "CREATE TABLE IF NOT EXISTS record_201901(" \
              "id int(4) not null primary key auto_increment, " \
              "amt int(4) not null default 0);",

        ],
    }

    
    dbnames = ['test', 'test-1', 'test-2']


    for dbn in dbnames:
        with dbpool.get_connection(dbn) as conn:
            for s in sqls[dbn]:
                print(s)
                try:
                    conn.execute(s)
                except Exception as e:
                    if e.args[0] == 1051:
                        continue
                    raise



    tables = ['testme','testme1','testme2']
    with get_connection('test') as conn:
        for i in range(1, 4):
            t = random.choice(tables)
            conn.insert(t, {'id':i, 'name':'haha'+str(i), 'ctime':int(time.time())+i})

        for t in tables:
            ret = conn.query('select * from %s' % t)
            print(pprint.pformat(ret))

        
        print(conn.select('record_201908'))
        print(conn.select('record_201907'))
        print(conn.select('record_201906'))
        print(conn.select('record_201905'))
        
        try:
            log.debug("try trans")
            conn.start()
        except ShardingError as e:
            log.debug(e)



    with get_connection('test') as conn:
        print(conn.select("aaa"))
        print(conn.select("bbb"))
        print(conn.select("ccc"))

    log.debug('close, wait')
    time.sleep(10)


def test_main():
    import logger
    logger.install('stdout')
   
    test()

    print('complete!')



if __name__ == '__main__':
    test_main()

