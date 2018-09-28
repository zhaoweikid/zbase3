# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import os
import sys
HOME = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(os.path.dirname(HOME), 'bin')
sys.path.append(os.path.join(os.path.dirname(HOME), 'conf'))
sys.path.append(BIN)

import config as myconfig

bind = '%s:%s' % (myconfig.HOST, myconfig.PORT)
chdir = BIN
#daemon = True
workers = 1
threads = 8
#worker_class = 'sync'
worker_class = 'gevent'
backlog = 1024
timeout = 30
loglevel = 'info'

access_log_format = '%(t)s %(p)s %(h)s "%(r)s" %(s)s %(L)s %(b)s "%(f)s" "%(a)s"'
accesslog = os.path.join(HOME, '../log/gunicorn_access.log')
errorlog = os.path.join(HOME, '../log/gunicorn_error.log')
