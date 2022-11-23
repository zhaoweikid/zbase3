# coding:utf-8
# 各种id生成算法
import os, sys
import time
import struct
import binascii
import uuid
import base64
import threading
import datetime

# 生成64位整型唯一id
# msec(42b) + server_id(6b) + seq(16b)
# muse have a myql conn

def new_id64_base(seq, server_id=0):
    msec = int(time.time()*1000)
    return (msec << 22) + (server_id << 16) + seq

def new_id64_mysql(conn, server_id=0):
    ''' kwargs: conn - a mysql connection '''
    ret  = conn.get("select uuid_short()", isdict=False)
    uuid = ret[0]
    seq  = uuid % 65535;
    if server_id <= 0:
        server_id = conn.server_id
    return new_id64_base(seq, server_id)

def new_id64_redis(conn, server_id=0):
    ''' kwargs: conn - a redis connection '''
    key = 'zbase3.new_id64.{0}'.format(server_id)
    seq = conn.incr(key)
    seq  = seq % 65535;
    return new_id64_base(seq, server_id)


def new_id64(conn, server_id=0):
    return new_id64_mysql(conn, server_id)


def unpack_id64(xid):
    ''' xid - a id create by new_id64 '''
    msec = (xid >> 22)
    server_id = (xid >> 16) & 0x3f
    return msec, server_id

def unpack_id64_time(xid):
    ''' xid - a id create by new_id64 '''
    msec = (xid >> 22)
    return datetime.datetime.fromtimestamp(int(msec/1000.0))


# 生成20位时间顺序唯一字符串id。每秒最多生成1000万个
# create sequence number
# year(2)+month(2)+day(2)+server_id(1)+second(5)+seq(8)
# muse have a myql conn

def new_sn_base(seq, server_id=0):
    now  = datetime.datetime.now()
    t = datetime.datetime(now.year, now.month, now.day)
    seq = int(now.timestamp() - t.timestamp())*100000000 + seq
    return '{:2d}{:02d}{:02d}{:1d}{:013d}'.format(now.year-2000, now.month, now.day, server_id, seq)

def new_sn_mysql(conn, server_id=0):
    ''' kwargs: conn - a mysql connection '''
    ret  = conn.get("select uuid_short()", isdict=False)
    uuid = ret[0]
    if server_id <= 0:
        server_id = conn.server_id

    seq = (uuid & 0xffffff) % 100000000;
    return new_sn_base(seq, server_id)


def new_sn_redis(conn, server_id=0, key=''):
    ''' kwargs: conn - a mysql connection '''
    if key:
        mykey = 'zbase3.new_sn.{0}.{1}'.format(key, server_id)
    else:
        mykey = 'zbase3.new_sn.{0}'.format(server_id)
    seq = conn.incr(key) % 100000000
    return new_sn_base(seq, server_id)


def new_sn(conn, server_id=0):
    ''' kwargs: conn - a mysql connection '''
    return new_sn_mysql(conn, server_id)


def test_id64():
    from zbase3.base import logger, dbpool
    logger.install('stdout')
    DATABASE = {'test': # connection name, used for getting connection from pool
                {'engine':'pymysql',   # db type, eg: mysql, sqlite
                 'db':'test',        # db name
                 'host':'127.0.0.1', # db host
                 'port':3306,        # db port
                 'user':'test',      # db user
                 'passwd':'123456',  # db password
                 'charset':'utf8',   # db charset
                 'conn':2}          # db connections in pool
           }

    dbpool.install(DATABASE)

    print(datetime.datetime.now())
    with dbpool.get_connection('test') as conn:
        for i in range(0, 10):
            myid = new_id64(conn=conn)
            print("time:%s id:%d" % (str(datetime.datetime.now()), myid))
            unpack_id64(myid)
            print("unkpack time:%s" % unpack_id64_time(myid))

def test_sn():
    from zbase3.base import logger, dbpool
    logger.install('stdout')
    DATABASE = {'test': # connection name, used for getting connection from pool
                {'engine':'pymysql',   # db type, eg: mysql, sqlite
                 'db':'test',        # db name
                 'host':'127.0.0.1', # db host
                 'port':3306,        # db port
                 'user':'test',      # db user
                 'passwd':'123456',  # db password
                 'charset':'utf8',   # db charset
                 'conn':2}          # db connections in pool
           }

    dbpool.install(DATABASE)

    print(datetime.datetime.now())
    with dbpool.get_connection('test') as conn:
        for i in range(0, 10):
            myid = new_sn(conn=conn)
            print("time:%s id:%s" % (str(datetime.datetime.now()), myid))
            #time.sleep(1)

    import redis
    print('-'*20)
    conn = redis.StrictRedis(host='localhost', port=6379, db=0)
    print(new_id64_redis(conn))
    print(new_sn_redis(conn))
    print(len(new_sn_redis(conn)))



if __name__ == '__main__':
    test_sn()



