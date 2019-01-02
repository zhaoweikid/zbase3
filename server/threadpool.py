# coding: utf-8
import string, sys, os, time
import threading
oldname = threading._newname
def _myname(template='T%d'):
    return oldname(template)
threading._newname = _myname
import queue, traceback
import logging

TASK_NORET = 0
TASK_RET   = 1
TASK_NOTIFY_RET = 2

log = logging.getLogger()

class ThreadPool:
    def __init__(self, num, qsize=0):
        self.queue   = queue.Queue(qsize)
        self.result  = {}
        self.threads = []
        self.count   = num
        #self.mutex   = threading.Lock()

        self.isrunning  = False
        self.task_done  = 0
        self.task_error = 0
        # 正在执行任务的线程数
        #self.thread_running = 0

    def start(self):
        # 如果标记为已经在运行就不能再创建新的线程池运行了
        if self.isrunning:
            return
        for i in range(0, self.count):
            t = threading.Thread(target=self._run)
            self.threads.append(t)
            #t.setDaemon(True)

        self.isrunning = True
        for th in self.threads:
            th.start()

    def stop(self):
        self.isrunning = False
        log.info('wait stop threadpool ...')
        while self.queue.qsize() > 0:
            time.sleep(1)

        for t in self.threads:
            t.join()
        log.info('threadpool stopped')

    def _run(self):
        while True:
            try:
                task = self.queue.get(timeout=1)
                #task = self.queue.get()
                if not task:
                    log.error('get task none')
                    return
                self.do_task(task)
            except queue.Empty:
                if not self.isrunning:
                    log.info('stop!')
                    return
            except Exception as e:
                #log.info('get timeout, self.queue.get:',  str(e))
                continue


    def do_task(self, task):
        #log.debug('get task: %s' % (task.name))
        #self.thread_running += 1

        try:
            ret = task.run()
        except Exception as e:
            log.error('task %s run error: %s' % (task.name, str(e)))
            #traceback.print_exc(file=sys.stdout)
            log.error(traceback.format_exc())
            #self.thread_running -= 1
            #self.task_error += 1
            return

        #self.task_done += 1
        #self.thread_running -= 1

        if not ret is None:
            task.set_result(ret)

        #log.debug('task %s run complete' % task.name)

    def add(self, task):
        self.queue.put(task)

    def info(self):
        return (self.task_done, self.task_error)


class Task (object):
    def __init__(self, func=None, *args, **kwargs):
        self.name = self.__class__.__name__
        self._func = func
        self._args = args
        self._kwargs = kwargs

        self._result  = None

    def run(self):
        return self._func(self, *self._args, **self._kwargs)

    def set_result(self, result):
        self._result = result

    def get_result(self, timeout=1000):
        return self._result



class TaskWait(Task):
    def __init__(self, func=None, *args, **kwargs):
        super(TaskWait, self).__init__(func, *args, **kwargs)
        self._event = threading.Event()

    def set_result(self, result):
        self._result = result
        self._event.set()

    def get_result(self, timeout=1000):
        try:
            #log.info('wait ...')
            self._event.wait(timeout/1000.0)
            #log.info('wait timeout ...')
        except:
            log.info(traceback.format_exc())
            return None
        return self._result


class SimpleTask(Task):
    def __init__(self, n, a=None):
        self.name = n
        super(SimpleTask, self).__init__(a)

    def run(self):
        #log.info('in task run, ', self.name)
        time.sleep(1)
        #log.info('ok, end task run', self.name)

        return self.name

def test():
    from zbase3.base import logger
    global log
    log = logger.install('ScreenLogger')
    tp = ThreadPool(10)

    for i in range(0, 100):
        t = SimpleTask(str(i))
        tp.add(t)

    tp.start()
    while True:
        done, error = tp.info()
        log.info('applys:', done, error)
        cc = done + error
        time.sleep(1)
        if cc == 100:
            break
    tp.stop()
    log.info('end')

def test1():
    from zbase3.base import logger
    global log
    log = logger.install('stdout')
    log.info('init')
    tp = ThreadPool(10)
    tp.start()

    class SimpleTask2(Task):
        def __init__(self, n, a=None):
            self.name = n
            super(SimpleTask2, self).__init__(a)

        def run(self):
            log.info('in task run, %s', self.name)
            time.sleep(2)
            log.info('ok, end task run %s', self.name)
            return self.name + '!!!'

    t = SimpleTask2('haha')
    log.info('add ...')
    tp.add(t)

    log.info('result:%s', t.get_result(1000))

    tp.stop()

def test2():
    from zbase3.base import logger
    global log
    log = logger.install('stdout')
    log.info('init')
    tp = ThreadPool(10)
    tp.start()

    def run(obj, name):
        log.info('in task run, %s', name)
        time.sleep(1)
        log.info('ok, end task run %s', name)
        return name + '!!!'

    log.info('add ...')
    t = TaskWait(func=run, name='haha')
    tp.add(t)

    log.info('result:%s', t.get_result(2))

    tp.stop()

def test3():
    from zbase3.base import logger
    global log
    log = logger.install('stdout')
    log.info('init')
    tp = ThreadPool(10)
    tp.start()

    def run(obj, name):
        #log.info('in task run, %s', name)
        #time.sleep(1)
        #log.info('ok, end task run %s', name)
        return name+'!!!'

    log.info('add ...')
    t = Task(func=run, name='haha')
    tp.add(t)

    log.info('result:%s', t.get_result(1000))


    # test
    n = 100000

    # local
    tstart = time.time()
    for i in xrange(0, n):
        t = Task(func=run, name='haha')
        run(None, 'haha')
    tend = time.time()

    print('local call ## time:%.6f qps:%d avg:%d' % (tend-tstart, n/(tend-tstart), ((tend-tstart)/n)*1000000))

    # queue
    q = queue.Queue()
    tstart = time.time()
    for i in xrange(0, n):
        q.put(run(None, 'haha'), timeout=1)
        q.get()
    tend = time.time()

    print('queue call ## time:%.6f qps:%d avg:%d' % (tend-tstart, n/(tend-tstart), ((tend-tstart)/n)*1000000))


    # thread, task no wait
    tstart = time.time()
    for i in xrange(0, n):
        t = Task(func=run, name='haha')
        tp.add(t)
        #t.get_result(100)
    tend = time.time()

    print('thread call ## time:%.6f qps:%d avg:%d' % (tend-tstart, n/(tend-tstart), ((tend-tstart)/n)*1000000))

    # thread, task wait

    tp.stop()
    log.info('==== end ====')


def test_profile():
    import cProfile

    cProfile.run('test3()', 'result')

if __name__ == '__main__':
    try:
        #test_profile()
        test2()
    except KeyboardInterrupt:
        os.kill(os.getpid(), 9)



