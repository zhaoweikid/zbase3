# coding: utf-8
import sys, os
import types
import logging
import logging.config
import logging.handlers
from logging.handlers import TimedRotatingFileHandler
from logging import DEBUG, INFO, WARN, ERROR, FATAL, NOTSET
from stat import ST_DEV, ST_INO, ST_MTIME
import time
import threading
import uuid
    
#threading._main_thread.name = 'MT'
threading.current_thread().setName('MT')

LEVEL_COLOR = {
    DEBUG: '\33[2;39m',
    INFO: '\33[0;36m',
    WARN: '\33[0;33m',
    ERROR: '\33[0;35m',
    FATAL: '\33[1;31m',
    NOTSET: ''
}

log = None

REQUEST_ID_MAP = {}



uuid_chars = ("a", "b", "c", "d", "e", "f",
             "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s",
             "t", "u", "v", "w", "x", "y", "z", "0", "1", "2", "3", "4", "5",
             "6", "7", "8", "9", "A", "B", "C", "D", "E", "F", "G", "H", "I",
             "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V",
             "W", "X", "Y", "Z")

def short_uuid():
    uuidstr = uuid.uuid4().hex
    result = ''
    for i in range(0, 8):
        sub = uuidstr[i*4: i*4+4]
        x = int(sub, 16)
        result += uuid_chars[x % 0x3E]
    return result

def set_req_id(reqid=None):
    global REQUEST_ID_MAP
    current_id = threading.current_thread().name
    REQUEST_ID_MAP[current_id] = reqid or short_uuid()

def get_req_id():
    global REQUEST_ID_MAP
    current_id = threading.current_thread().name
    return REQUEST_ID_MAP.get(current_id, '')


class ScreenHandler(logging.StreamHandler):
    def set_r_id(self, record):
        req_id = get_req_id() or '-'
        record.requestId = req_id

    def emit(self, record):
        try: 
            self.set_r_id(record)
            msg = self.format(record)
            stream = self.stream
            fs = LEVEL_COLOR[record.levelno] + "%s\n" + '\33[0m'
            stream.write(fs % msg) 
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except: 
            self.handleError(record)


class MyTimedRotatingHandler (TimedRotatingFileHandler):

    def __init__(self, filename, when='h', interval=1, backupCount=0,
                 encoding=None, delay=False, utc=False, atTime=None,
                 errors=None):
        TimedRotatingFileHandler.__init__(self, filename, when, interval, backupCount, encoding, delay, utc)

        self.dev, self.ino = -1, -1
        self._check_time = 0
        self._statstream()

    def set_r_id(self, record):
        req_id = get_req_id() or '-'
        record.requestId = req_id


    def emit(self, record):
        """
        Emit a record.

        If underlying file has changed, reopen the file before emitting the
        record to it.
        """

        self.set_r_id(record)
        self.reopenIfNeeded()
        TimedRotatingFileHandler.emit(self, record)



    def doRollover(self):
        """
        do a rollover; in this case, a date/time stamp is appended to the filename
        when the rollover happens.  However, you want the file to be named for the
        start of the interval, not the current time.  If there is a backup count,
        then we have to get a list of matching filenames, sort them and remove
        the one with the oldest suffix.
        """
        if self.stream:
            self.stream.close()
            self.stream = None
        # get the time that this sequence started at and make it a TimeTuple
        currentTime = int(time.time())
        dstNow = time.localtime(currentTime)[-1]
        t = self.rolloverAt - self.interval
        if self.utc:
            timeTuple = time.gmtime(t)
        else:
            timeTuple = time.localtime(t)
            dstThen = timeTuple[-1]
            if dstNow != dstThen:
                if dstNow:
                    addend = 3600
                else:
                    addend = -3600
                timeTuple = time.localtime(t + addend)
        dfn = self.baseFilename + "." + time.strftime(self.suffix, timeTuple)
        if hasattr(self, 'rotation_filename'):
            dfn = self.rotation_filename(self.baseFilename + "." +
                                     time.strftime(self.suffix, timeTuple))
        if not os.path.exists(dfn):
            #os.remove(dfn)
            try:
                if hasattr(self, 'rotate'):
                    self.rotate(self.baseFilename, dfn)
                else:
                    os.rename(self.baseFilename, dfn)
            except:
                pass
            else:
                if self.backupCount > 0:
                    for s in self.getFilesToDelete():
                        try:
                            os.remove(s)
                        except:
                            pass
        #if not self.delay:
        #    self.stream = self._open()
        #    self._statstream()
        self.stream = self._open()
        self._statstream()

        newRolloverAt = self.computeRollover(currentTime)
        while newRolloverAt <= currentTime:
            newRolloverAt = newRolloverAt + self.interval
        #If DST changes and midnight or weekly rollover, adjust for this.
        if (self.when == 'MIDNIGHT' or self.when.startswith('W')) and not self.utc:
            dstAtRollover = time.localtime(newRolloverAt)[-1]
            if dstNow != dstAtRollover:
                if not dstNow:  # DST kicks in before next rollover, so we need to deduct an hour
                    addend = -3600
                else:           # DST bows out before next rollover, so we need to add an hour
                    addend = 3600
                newRolloverAt += addend
        self.rolloverAt = newRolloverAt


    def _statstream(self):
        if self.stream:
            sres = os.fstat(self.stream.fileno())
            self.dev, self.ino = sres[ST_DEV], sres[ST_INO]

    def reopenIfNeeded(self):
        """
        Reopen log file if needed.

        Checks if the underlying file has changed, and if it
        has, close the old stream and reopen the file to get the
        current stream.
        """
        # Reduce the chance of race conditions by stat'ing by path only
        # once and then fstat'ing our new fd if we opened a new log stream.
        # See issue #14632: Thanks to John Mulligan for the problem report
        # and patch.

        now = int(time.time())
        if now - self._check_time < 60:
            return
        else:
            self._check_time = now

        try:
            # stat the file by path, checking for existence
            sres = os.stat(self.baseFilename)
        except FileNotFoundError:
            sres = None
        # compare file system stat with that of our stream file handle
        if not sres or sres[ST_DEV] != self.dev or sres[ST_INO] != self.ino:
            self._reopen()

    def _reopen(self):
        if self.stream is not None:
            # we have an open file handle, clean it up
            self.stream.flush()
            self.stream.close()
            self.stream = None  # See Issue #21742: _open () might fail.
            # open a new file handle and get new stat info from that fd
            self.stream = self._open()
            self._statstream()




logging.ScreenHandler = ScreenHandler
logging.MyTimedRotatingHandler = MyTimedRotatingHandler

def debug(msg, *args, **kwargs):
    global log
    log.debug(msg, *args, **kwargs)

# 使用新的format方式, 以下i, w, e, f同样
def d(msg, *args, **kwargs):
    global log
    log.debug(msg.format(*args, **kwargs))

def info(msg, *args, **kwargs):
    global log
    log.info(msg, *args, **kwargs)

def i(msg, *args, **kwargs):
    global log
    log.info(msg.format(*args, **kwargs))

def warn(msg, *args, **kwargs):
    global log
    log.warning(msg, *args, **kwargs)
warning = warn

def w(msg, *args, **kwargs):
    global log
    log.warning(msg.format(*args, **kwargs))

def error(msg, *args, **kwargs):
    global log
    log.error(msg, *args, **kwargs)

def e(msg, *args, **kwargs):
    global log
    log.error(msg.format(*args, **kwargs))

def fatal(msg, *args, **kwargs):
    global log
    log.fatal(msg, *args, **kwargs)
critical = fatal

def f(msg, *args, **kwargs):
    global log
    log.fatal(msg.format(*args, **kwargs))
c = f


def create_log_conf(options, name, level='DEBUG'):
    filecf = {
        'class': 'logging.MyTimedRotatingHandler',
        'formatter': 'myformat',
        'level': level.upper(),
        'filename': name,
    }
    if options:
        filecf.update(options)
    if 'when' not in filecf:
        filecf['when'] = 'MIDNIGHT'
    if 'backupCount' not in filecf:
        filecf['backupCount'] = 10
    return filecf


def install(logdict, **options):
    if isinstance(logdict, str):
        logdict = {
            'root':{
                'filename':logdict,
            }
        }
        if options:
            logdict['root'].update(options)

    conf = { 
        'version': 1,
        'formatters': {
            'myformat': {
                'format': '%(asctime)s %(process)d,%(threadName)s %(requestId)s %(filename)s:%(lineno)d [%(levelname).1s] %(message)s',
            },  
        },  
        'handlers': {
            'console': {
                'class': 'logging.ScreenHandler',
                'formatter': 'myformat',
                'level': 'DEBUG',
                'stream': 'ext://sys.stdout',
            },  
        },  
        'loggers': {
        },  
        'root':{
            'level':'DEBUG',
            'handlers': [],
        }
    }

    for logname,onecf in logdict.items():
        cf = conf.get(logname)
        if not cf:
            cf = {'handlers':[]}
            conf[logname] = cf

        filename = onecf['filename']
        if isinstance(filename, str):
            fbasename = os.path.basename(filename)
            if filename == 'stdout': 
                cf['handlers'].append('console')
            else:
                name = 'file-'+fbasename
                conf['handlers'][name] = create_log_conf(options, filename)
                cf['handlers'] = [name]
        else:
            for level,fname in filename.items():
                name = 'file-'+os.path.basename(fname)
                conf['handlers'][name] = create_log_conf(options, fname, level)
                cf['handlers'].append(name)
    
    for logname in logdict:
        if logname != 'root':
            logobj = logging.getLogger(logname)
            logobj.propagate = False

    logging.config.dictConfig(conf)
    logobj = logging.getLogger() 
    global log
    log = logobj
    return logobj


# 简单配置方式只能配置root的logger
# logdict: 可以为字符串(例如: test.log 或 stdout)或者字典(例如:{'DEBUG':filename, 'WARN':filename})
def simple_install(logdict, **options):
    if isinstance(logdict, str):
        logdict = {'DEBUG': logdict}

    conf = { 
        'version': 1,
        'formatters': {
            'myformat': {
                'format': '%(asctime)s %(process)d,%(threadName)s %(filename)s:%(lineno)d [%(levelname).1s] %(message)s',
            },  
        },  
        'handlers': {
            'console': {
                'class': 'logging.ScreenHandler',
                'formatter': 'myformat',
                'level': 'DEBUG',
                'stream': 'ext://sys.stdout',
            },  
        },  
        'loggers': {
        },
        'root':{
            'level':'DEBUG',
            'handlers': [],
        }
    }

    rootcf = conf['root']
    for level,filename in logdict.items():
        if filename == 'stdout':
            rootcf['handlers'].append('console')
        else:
            name = 'file-'+filename
            conf['handlers'][name] = create_log_conf(options, filename, level)
            rootcf['handlers'].append(name)

    logging.config.dictConfig(conf)
    logobj = logging.getLogger() 
    global log
    log = logobj
    return logobj




def test_mlogger():
    install({
        'root': {
            'filename': {'DEBUG':"test.log", 'ERROR':'test-err.log'},
        },
        'mytest': {
            'filename':'stdout',
        },
    })

    log1 = logging.getLogger()
    for i in range(0, 10):
        log1.debug('debug ... %d', i)
        log1.info('info ... %d', i)
        log1.warning('warn ... %d', i)
        log1.error('error ... %d', i)
        log1.fatal('fatal ... %d', i)

    log2 = logging.getLogger('mytest')
    for i in range(0, 10):
        log2.debug('debug ... %d', i)
        log2.info('info ... %d', i)
        log2.warning('warn ... %d', i)
        log2.error('error ... %d', i)
        log2.fatal('fatal ... %d', i)


def test_base():
    install('stdout')
    log = logging.getLogger()
    for i in range(0, 10):
        log.debug('debug ... %d', i)
        log.info('info ... %d', i)
        log.warning('warn ... %d', i)
        log.error('error ... %d', i)
        log.fatal('fatal ... %d', i)


def test_root():
    import time
    install({'root':{'filename':{'DEBUG':'test.log', 'WARN':'test.warn.log'}}}, when="S", backupCount=3)
    log = logging.getLogger()
    for i in range(0, 10):
        log.debug('debug ... %d', i)
        log.info('info ... %d', i)
        log.warning('warn ... %d', i)
        log.error('error ... %d', i)
        log.fatal('fatal ... %d', i)
        time.sleep(1)

def test_simple():
    simple_install('stdout')

    log = logging.getLogger()
    for a in range(0, 10):
        log.debug('debug ... %d', a)
        log.info('info ... %d', a)
        log.warning('warn ... %d', a)
        log.error('error ... %d', a)
        log.fatal('fatal ... %d', a)

    for a in range(0, 10):
        d('debug ... {:02d}', a)
        i('info ... {:02d}', a)
        w('warn ... {:02d}', a)
        e('error ... {:02d}', a)
        f('fatal ... {:02d}', a)

def test_simple_file():
    simple_install('test.log')

    log = logging.getLogger()
    for i in range(0, 10):
        log.debug('debug ... %d', i)
        log.info('info ... %d', i)
        log.warning('warn ... %d', i)
        log.error('error ... %d', i)
        log.fatal('fatal ... %d', i)


def test_simple_mfile():
    simple_install({'DEBUG':'test.log', 'WARN':'test.warn.log'})

    log = logging.getLogger()
    for i in range(0, 10):
        log.debug('debug ... %d', i)
        log.info('info ... %d', i)
        log.warning('warn ... %d', i)
        log.error('error ... %d', i)
        log.fatal('fatal ... %d', i)

def test_simple_file_ro():
    simple_install('test.log', when='M', backupCount=3)

    log = logging.getLogger()
    i = 0
    while True:
        log.debug('debug ... %d', i)
        log.info('info ... %d', i)
        log.warning('warn ... %d', i)
        log.error('error ... %d', i)
        log.fatal('fatal ... %d', i)
        i += 1
        time.sleep(1)

def test_proc_file_ro():
    simple_install('test.log', when='M', backupCount=3)

    log = logging.getLogger()

    def dolog():
        i = 0
        while True:
            log.debug('debug ... %d', i)
            log.info('info ... %d', i)
            log.warning('warn ... %d', i)
            log.error('error ... %d', i)
            log.fatal('fatal ... %d', i)
            i += 1
            time.sleep(1)

    pid = os.fork()
    if pid < 0:
        print('fork error:%d', pid)
        return

    if pid == 0:
        dolog()
    else:
        dolog()

def test():
    if len(sys.argv) == 1:
        for x in globals():
            if x.startswith('test_'):
                print(x)
    else:
        globals()[sys.argv[1]]()

if __name__ == '__main__':
    test()

