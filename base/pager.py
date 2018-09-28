# coding: utf-8
import sys, os
import copy, traceback
import math
import logging

log = logging.getLogger()

class Pager:
    '''分页类'''
    def __init__(self, data, page, pagesize=20):
        '''设置初始值
        data - data
        page - 当前页码
        pagesize - 每页显示条数
        '''
        self.pagedata = data
        if page <= 0:
            page = 1
        self.page = page

        self.count = -1
        self.page_size = pagesize
        self.pages = 0

    def split(self, isdict=True):
        '''分页'''
        if self.count == -1:
            self.count, self.pages = self.pagedata.count(self.page_size)

        self.pagedata.load(self.page, self.page_size, isdict)

    def todict(self):
        '''返回pagedata数据转换为字典'''
        self.split(True)
        #log.info('data:%s', self.pagedata.data)
        x = copy.copy(self.pagedata.data)
        for row in x:
            for k,v in row.items():
                if k.endswith('time'):
                    row[k] = str(v)
        return x

    def tolist(self):
        self.split(False)
        return self.pagedata.data

    def prev(self):
        '''前页页码'''
        if self.page == 1:
            return 0
        else:
            return self.page-1

    def have_prev(self):
        '''是否有前页'''
        if self.page <= 1:
            return False
        return True

    def next(self):
        '''后页页码'''
        if self.pages > 0 and self.page >= self.pages:
            return 0
        else:
            return self.page+1

    def have_next(self):
        '''是否有后页'''
        if self.pages > 0 and self.page >= self.pages:
            return False
        return True

    def first(self):
        '''第一页，页码是从1开始的'''
        return 1

    def last(self):
        '''最后一页页码'''
        if self.pages <= 0:
            return 1
        return self.pages

    def range(self, maxlen=10):
        '''显示一个页码返回，尽量把当前页放在中间'''
        if self.pages > 0:
            pagecount = self.pages
        else:
            pagecount = self.page + maxlen
        ret = range(max(self.page-maxlen, 1), min(self.page+maxlen, pagecount)+1)
        #log.info("range:", ret)
        return ret

    def pack(self):
        '''将数据打包到一个字典中'''
        r = {'prev':  self.prev(),
             'next':  self.next(),
             'first': self.first(),
             'last':  self.last(),
             'pages': self.pages,
             'page':  self.page,
             'count': self.count,
             'range': self.range}

        return r

    def show_html(self):
        pass

class PageDataBase:
    def load(self, cur, pagesize):
        pass

    def count(self, pagesize):
        pass

class PageDataDB (PageDataBase):
    def __init__(self, db, sql, count_sql=None, maxid=-1):
        '''设置初始值
        db  - 数据库连接对象
        sql - 分页查询sql
        pagesize - 每页显示条数
        maxid - 最大id
        '''
        self.db   = db
        self.data = []
        self.url  = ''
        self.maxid = maxid

        sql = sql.replace('%', '%%')
        # 如果设置了最大id，在查询的时候要加上限制，但是这里有问题。可能原来的分页sql已经有where了
        if maxid > 0:
            self.query_sql = sql + " where id<" + str(maxid) + " limit %d"
        else:
            self.query_sql = sql + " limit %d,%d"

        # 生成计算所有记录的sql
        if count_sql:
            self.count_sql = count_sql
        else:
            backsql  = sql[sql.find(" from "):]
            orderpos = backsql.find(' order by ')
            # 去掉order，统计记录数order没用
            if orderpos > 0:
                backsql = backsql[:orderpos]
            self.count_sql = "select count(*) as count " + backsql
        self.records = -1

    def load(self, cur, pagesize, isdict=False):
        '''加载数据'''
        if self.maxid >= 0:
            sql = self.query_sql % (pagesize)
        else:
            sql = self.query_sql % ((cur-1)*pagesize, pagesize)
        log.info('PageDataDB load sql:%s', sql)
        self.data = self.db.query(sql, isdict=isdict)
        return self.data

    def count(self, pagesize):
        '''统计页数'''
        # 没有统计页数的sql，说明不需要计算总共多少页
        #log.info("PageDataDB count sql:%s", self.count_sql)
        ret = self.db.query(self.count_sql)
        row = ret[0]
        self.records = int(row['count'])
        log.info("PageDataDB count:%s", self.records)
        a = divmod(self.records, pagesize)
        if a[1] > 0:
            page_count = a[0] + 1
        else:
            page_count = a[0]
        return self.records, page_count


def db_pager(db, sql, pagecur, pagesize, count_sql=None, maxid=-1):
    pgdata = PageDataDB(db, sql, count_sql, maxid)
    p = Pager(pgdata, pagecur, pagesize)
    return p




