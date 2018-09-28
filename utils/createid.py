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

# msec(42b) + server_id(6b) + seq(16b)
# muse have a myql conn
def new_id64(**kwargs):
    ''' kwargs: conn - a mysql connection '''
    conn = kwargs['conn']
    msec = int(time.time()*1000)
    ret  = conn.get("select uuid_short()", isdict=False)
    uuid = ret[0]
    seq  = uuid % 65535;
    return (msec << 22) + (conn.server_id << 16) + seq

def unpack_id64(xid):
    ''' xid - a id create by new_id64 '''
    msec = (xid >> 22)
    server_id = (xid >> 16) & 0x3f
    return msec, server_id

def unpack_id64_time(xid):
    ''' xid - a id create by new_id64 '''
    msec = (xid >> 22)
    return datetime.datetime.fromtimestamp(int(msec/1000.0))

def test():
    from zbase3.base import logger, dbpool
    logger.install('stdout')
    DATABASE = {'test': # connection name, used for getting connection from pool
                {'engine':'pymysql',   # db type, eg: mysql, sqlite
                 'db':'test',        # db name
                 'host':'127.0.0.1', # db host
                 'port':3306,        # db port
                 'user':'root',      # db user
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

if __name__ == '__main__':
    test()



