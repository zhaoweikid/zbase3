# coding: utf-8
import os, sys, types
import base64
import socket
import logging
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from email.utils import COMMASPACE,formatdate
import smtplib

log = logging.getLogger()

class MailMessage:
    '''邮件消息内容'''
    def __init__(self, subject, fromaddr, toaddr, content):
        self.mailfrom = fromaddr
        self.mailto = toaddr

        self.msg = MIMEMultipart()
        self.msg['From'] = fromaddr
        # self.msg['Subject'] = '=?UTF-8?B?%s?=' % (base64.b64encode(subject.encode('utf-8')))
        self.msg['Subject'] = Header(subject, 'utf-8')

        if type(toaddr) in (tuple, list):
            self.msg['To'] = COMMASPACE.join(toaddr)
        else:
            self.msg['To'] = toaddr
        self.msg['Date'] = formatdate(localtime=True)
        if content.find('<') >= 0 and content.find('>') > 0:
            self.msg.attach(MIMEText(content, 'html', 'utf-8'))
        else:
            self.msg.attach(MIMEText(content, 'plain', 'utf-8'))

    def append_file(self, filename, conttype):
        '''增加文件附件'''
        #if isinstance(filename,types.UnicodeType):
        #    filename = filename.encode('utf-8')
        base_filename = os.path.basename(filename)
        maintype, subtype = conttype.split('/')
        part = MIMEBase(maintype, subtype, charset='utf-8')
        part.set_payload(open(filename, 'rb').read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=base_filename)
        self.msg.attach(part)

    def append_data(self, content, conttype='application/octet-stream', attachname=''):
        '''增加数据附件'''
        maintype, subtype = conttype.split('/')
        part = MIMEBase(maintype, subtype)
        part.set_payload(content)
        encoders.encode_base64(part)
        if attachname:
            part.add_header('Content-Disposition', 'attachment', filename=attachname)
        self.msg.attach(part)

    def tostring(self):
        return self.msg.as_string()

class MailSender:
    '''邮件发送'''
    def __init__(self, server, username, password):
        self.smtpserver = server
        self.username   = username
        self.password   = password

    def send(self, msg, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
        '''实际发送邮件，msg为一个MailMessage对象'''
        try:
            conn = smtplib.SMTP(self.smtpserver, timeout=timeout)
            #conn.set_debuglevel(1)
            conn.login(self.username, self.password)
            conn.sendmail(msg.mailfrom, msg.mailto, msg.tostring())
            conn.quit()
            log.info('mail to:%s send succeed!', str(msg.mailto))
            return True
        except Exception as e:
            log.warn('mail to:%s send error! %s', str(msg.mailto), str(e))
            return False

def sendmail(mailto, subject, content, files=None, timeout=socket._GLOBAL_DEFAULT_TIMEOUT):
    m = MailMessage(subject, 'receipt@xx.net', mailto, content)

    if files:
        if isinstance(files, (tuple, list)):
            for file in files:
                m.append_file(file, 'application/octet-stream')
        elif isinstance(files, str):
            m.append_file(files, 'application/octet-stream')

    sender = MailSender('smtp.exmail.qq.com', 'receipt@xx.net', '')
    return sender.send(m, timeout=timeout)

def sendmail_from(frominfo, mailto, subject, content, files=None):
    # mailfrom: {'smtp':xx,'from':xx,'password':xx}
    m = MailMessage(subject, frominfo['from'], mailto, content)

    if files:
        if isinstance(files, (tuple, list)):
            for file in files:
                m.append_file(file, 'application/octet-stream')
        elif isinstance(files, str):
            m.append_file(files, 'application/octet-stream')

    sender = MailSender(frominfo['smtp'], frominfo['from'], frominfo['password'])
    return sender.send(m)

def sendmail_balance(frominfos, mailto, subject, content, files=None):
    for info in frominfos:
        try:
            ret = sendmail_from(info, mailto, subject, content, files)
            if not ret:
                continue
            return ret
        except:
            continue

def test():
    m = MailMessage('test测试邮件', 'receipt@test.net', 'zhaowei@test.net', 'test content我们')
    m.append_file('mail.py', 'text/plain')
    print(m.tostring())

    sender = MailSender('smtp.exmail.qq.com', 'receipt@xx.net', '')
    sender.send(m)

def test1():
    from zbase3.base import logger
    logger.install('stdout')
    sendmail_balance(
            [
             {'smtp':'smtp.exmail.qq.com', 'from':'yuanyuejiang@test.com', 'password':''},
             {'smtp':'smtp.exmail.qq.com', 'from':'zhangshuang@test.com', 'password':''},
            ],
            'yuanyuejiang@test.com', 'haha', 'content test 222')

def test_attachment():
    m = MailMessage('test测试邮件', 'receipt@xx.net', 'xiangwei@test.com', 'test content我们')
    f = open('mail.py', 'r')
    data = f.read()
    m.append_data(data, attachname='mail.py')
    print(m.tostring())

    sender = MailSender('smtp.exmail.qq.com', 'receipt@xx.net', '')
    sender.send(m)
    f.close()


if __name__ == '__main__':
    #test1()
    test_attachment()


