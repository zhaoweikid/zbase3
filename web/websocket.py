"""
0                   1                   2                   3
0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
|     Extended payload length continued, if payload len == 127  |
+ - - - - - - - - - - - - - - - +-------------------------------+
|                               |Masking-key, if MASK set to 1  |
+-------------------------------+-------------------------------+
| Masking-key (continued)       |          Payload Data         |
+-------------------------------- - - - - - - - - - - - - - - - +
:                     Payload Data continued ...                :
+ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +
|                     Payload Data continued ...                |
+---------------------------------------------------------------+
~~~~~~~~~~
websocket 报文协议

"""

import struct
import logging
import traceback
from datetime import datetime

from socket import error


log = logging.getLogger()


class WebSocketError(error):
    """
    Base class for all websocket errors.
    """


class ProtocolError(WebSocketError):
    """
    Raised if an error occurs when de/encoding the websocket protocol.
    """

class WebSocketAddressException(WebSocketError):
    """
    If the websocket address info cannot be found, this exception will be raised.
    """
    pass


class FrameTooLargeException(ProtocolError):
    """
    Raised if a frame is received that is too large.
    """

class WebSocketException(Exception):
    """
    WebSocket exception class.
    """
    pass


class WebSocketProtocolException(WebSocketError):
    """
    If the WebSocket protocol is invalid, this exception will be raised.
    """
    pass


class WebSocketPayloadException(WebSocketError):
    """
    If the WebSocket payload is invalid, this exception will be raised.
    """
    pass


class WebSocketConnectionClosedException(WebSocketError):
    """
    If remote host closed the connection or some network error happened,
    this exception will be raised.
    """
    pass


class WebSocketTimeoutException(WebSocketError):
    """
    WebSocketTimeoutException will be raised at socket timeout during read/write data.
    """
    pass


class WebSocketProxyException(WebSocketError):
    """
    WebSocketProxyException will be raised when proxy error occurred.
    """
    pass


class WebSocketBadStatusException(WebSocketError):
    """
    WebSocketBadStatusException will be raised when we get bad handshake status code.
    """

    def __init__(self, message, status_code, status_message=None, resp_headers=None):
        msg = message % (status_code, status_message)
        super().__init__(msg)
        self.status_code = status_code
        self.resp_headers = resp_headers


class WebSocketAddressException(WebSocketError):
    """
    If the websocket address info cannot be found, this exception will be raised.
    """
    pass





MSG_SOCKET_DEAD = "Socket is dead"
MSG_ALREADY_CLOSED = "Connection is already closed"
MSG_CLOSED = "Connection closed"


class WebSocket(object):

    __slots__ = ('environ', 'closed', 'stream', 'raw_write', 'raw_read', 'handler', 'ping_time')

    OPCODE_CONTINUATION = 0x00  # 附加数据帧
    OPCODE_TEXT = 0x01  # 文本数据帧 utf-8编码
    OPCODE_BINARY = 0x02  # 二进制
    OPCODE_CLOSE = 0x08 # close
    OPCODE_PING = 0x09 # ping
    OPCODE_PONG = 0x0a # pong

    def __init__(self, environ, stream, handler):
        self.environ = environ
        self.closed = False

        self.stream = stream

        self.raw_write = stream.write
        self.raw_read = stream.read

        self.ping_time = None

        self.handler = handler

    def __del__(self):
        try:
            if not self.closed:
                self.close()
        except:
            # close() may fail if __init__ didn't complete
            pass

    def _decode_bytes(self, bytestring):
        if not bytestring:
            return ''

        try:
            return bytestring.decode('utf-8')
        except UnicodeDecodeError:
            self.close(1007)

            raise

    def _encode_bytes(self, text):
        if not isinstance(text, str):
            text = str(text or '')

        return text.encode("utf-8")

    def _is_valid_close_code(self, code):
        """验证关闭close码是否正确
        """
        if code < 1000:
            return False

        if 1004 <= code <= 1006:
            return False

        if 1012 <= code <= 1016:
            return False

        if code == 1100:
            return False

        if 2000 <= code <= 2999:
            return False

        return True

    @property
    def current_app(self):
        class MockApp():
            def on_close(self, *args):
                pass

        return MockApp()

    def handle_close(self, header, payload):
        if not payload:
            self.close(1000, None)

            return

        if len(payload) < 2:
            raise ProtocolError('Invalid close frame: {0} {1}'.format(
                header, payload))

        code = struct.unpack('!H', payload[:2])[0]
        payload = payload[2:]

        if payload:
            # 如果发送close 信息 肯定是uft编码
            self._decode_bytes(payload)

        # 判断close码是否正确
        if not self._is_valid_close_code(code):
            raise ProtocolError('Invalid close code {0}'.format(code))
        self.close(code, payload)

    def handle_ping(self, header, payload):
        """服务端处理ping请求
        """
        self.send_frame(payload, self.OPCODE_PONG)

    def send_ping(self, header, payload):
        """客户端发送ping
        """
        self.send_frame(payload, self.OPCODE_PING)

    def handle_pong(self, header, payload):
        """客户端收到pong消息
        """
        self.ping_time = datetime.now()

    def read_frame(self):

        header = Header.decode_header(self.stream)

        # 不处理rsv 信息
        if header.flags:
            raise ProtocolError

        # 没有长度
        if not header.length:
            return header, b''

        try:
            payload = self.raw_read(header.length)
        except error:
            payload = b''
        except Exception:
            # TODO log out this exception
            payload = b''

        if len(payload) != header.length:
            raise WebSocketError('Unexpected EOF reading frame payload')

        if header.mask:
            payload = header.unmask_payload(payload)

        return header, payload

    def read_message(self):
        opcode = None
        message = bytearray()
        while True:
            header, payload = self.read_frame()
            log.debug('opcode:%s|payload:%s', header.opcode, payload)
            f_opcode = header.opcode

            if f_opcode in (self.OPCODE_TEXT, self.OPCODE_BINARY):
                opcode = f_opcode
                message += payload
                if f_opcode == self.OPCODE_TEXT:
                    return self._decode_bytes(message)
                else:
                    return message
            # 多帧 后面都是持续帧 目前不处理多帧情况
            elif f_opcode == self.OPCODE_CONTINUATION:
                if not opcode:
                    raise ProtocolError("Unexpected frame with opcode=0")

            elif f_opcode == self.OPCODE_PING:
                self.handle_ping(header, payload)
                continue

            elif f_opcode == self.OPCODE_PONG:
                self.handle_pong(header, payload)
                continue

            elif f_opcode == self.OPCODE_CLOSE:
                self.handle_close(header, payload)
                return

            else:
                raise ProtocolError("Unexpected opcode={0!r}".format(f_opcode))
            if header.fin:
                break

    def receive(self):
        if self.closed:
            self.current_app.on_close(MSG_ALREADY_CLOSED)
            raise WebSocketError(MSG_ALREADY_CLOSED)

        try:
            data = self.read_message()
            return data
        except UnicodeError:
            self.close(1007)
        except ProtocolError:
            self.close(1002)
        except error:
            self.close()
            self.current_app.on_close(MSG_CLOSED)
        return None

    def send_frame(self, message, opcode):
        if self.closed:
            self.current_app.on_close(MSG_ALREADY_CLOSED)
            raise WebSocketError(MSG_ALREADY_CLOSED)

        if opcode in (self.OPCODE_TEXT, self.OPCODE_PING):
            message = self._encode_bytes(message)
        elif opcode == self.OPCODE_BINARY:
            message = bytes(message)

        header = Header.encode_header(True, opcode, b'', len(message), 0)

        try:
            self.raw_write(header + message)
        except error:
            raise WebSocketError(MSG_SOCKET_DEAD)
        except:
            raise

    def send(self, message, binary=None):
        if binary is None:
            binary = not isinstance(message, str)

        opcode = self.OPCODE_BINARY if binary else self.OPCODE_TEXT

        try:
            self.send_frame(message, opcode)
        except WebSocketError:
            self.current_app.on_close(MSG_SOCKET_DEAD)
            raise WebSocketError(MSG_SOCKET_DEAD)

    def close(self, code=1000, message=b''):
        if self.closed:
            self.current_app.on_close(MSG_ALREADY_CLOSED)
            return

        try:
            message = self._encode_bytes(message)

            self.send_frame(message, opcode=self.OPCODE_CLOSE)
            log.info('websocket close')
        except WebSocketError:
            # Failed to write the closing frame but it's ok because we're
            # closing the socket anyway.
            log.debug("Failed to write closing frame -> closing socket")
        finally:
            self.closed = True

            self.stream = None
            self.raw_write = None
            self.raw_read = None

            self.environ = None


class Stream(object):

    __slots__ = ('handler', 'read', 'write')

    def __init__(self, handler):
        self.handler = handler
        self.read = handler.rfile.read
        self.write = handler.socket.sendall


class Header(object):
    __slots__ = ('fin', 'mask', 'opcode', 'flags', 'length')

    FIN_MASK = 0x80
    OPCODE_MASK = 0x0f
    MASK_MASK = 0x80
    LENGTH_MASK = 0x7f

    RSV0_MASK = 0x40
    RSV1_MASK = 0x20
    RSV2_MASK = 0x10

    HEADER_FLAG_MASK = RSV0_MASK | RSV1_MASK | RSV2_MASK

    def __init__(self, fin=0, opcode=0, flags=0, length=0):
        self.mask = ''
        self.fin = fin
        self.opcode = opcode
        self.flags = flags
        self.length = length

    def mask_payload(self, payload):
        payload = bytearray(payload)
        mask = bytearray(self.mask)

        for i in range(self.length):
            payload[i] ^= mask[i % 4]

        return payload

    unmask_payload = mask_payload

    @classmethod
    def decode_header(cls, stream):
        read = stream.read
        # 读前两个字节  16bit
        data = read(2)

        if len(data) != 2:
            raise WebSocketError("Unexpected EOF while decoding header")

        first_byte, second_byte = struct.unpack('!BB', data)

        header = cls(
            fin=first_byte & cls.FIN_MASK == cls.FIN_MASK,  # fin 为1 代表结束
            opcode=first_byte & cls.OPCODE_MASK,   # 获取opcode
            flags=first_byte & cls.HEADER_FLAG_MASK, # 获取rsv 操作信息
            length=second_byte & cls.LENGTH_MASK) # 获取payload len 数值

        has_mask = second_byte & cls.MASK_MASK == cls.MASK_MASK # 判断是否对payloadData 进行掩码处理

        # 0x07 之后都是 连接关闭 ping pong 所以都是fin都应该是消息结果 并且length不应该超过125
        if header.opcode > 0x07:
            if not header.fin:
                raise ProtocolError(
                    "Received fragmented control frame: {0!r}".format(data))

            # Control frames MUST have a payload length of 125 bytes or less
            if header.length > 125:
                raise FrameTooLargeException(
                    "Control frame cannot be larger than 125 bytes: "
                    "{0!r}".format(data))

        # 如果126 读取后2个字节为长度
        if header.length == 126:
            data = read(2)

            if len(data) != 2:
                raise WebSocketError('Unexpected EOF while decoding header')

            # 获取无符号整形数字
            header.length = struct.unpack('!H', data)[0]
        # 如果126 读取后8个字节为长度
        elif header.length == 127:
            # 64 bit length
            data = read(8)

            if len(data) != 8:
                raise WebSocketError('Unexpected EOF while decoding header')

            # 获取无符号长整形数字
            header.length = struct.unpack('!Q', data)[0]

        if has_mask:
            mask = read(4)

            if len(mask) != 4:
                raise WebSocketError('Unexpected EOF while decoding header')

            header.mask = mask

        return header

    @classmethod
    def encode_header(cls, fin, opcode, mask, length, flags):
        first_byte = opcode
        second_byte = 0
        extra = b""
        result = bytearray()

        if fin:
            first_byte |= cls.FIN_MASK

        if flags & cls.RSV0_MASK:
            first_byte |= cls.RSV0_MASK

        if flags & cls.RSV1_MASK:
            first_byte |= cls.RSV1_MASK

        if flags & cls.RSV2_MASK:
            first_byte |= cls.RSV2_MASK

        # now deal with length complexities
        if length < 126:
            second_byte += length
        elif length <= 0xffff:
            second_byte += 126
            extra = struct.pack('!H', length)
        elif length <= 0xffffffffffffffff:
            second_byte += 127
            extra = struct.pack('!Q', length)
        else:
            raise FrameTooLargeException

        if mask:
            second_byte |= cls.MASK_MASK

        result.append(first_byte)
        result.append(second_byte)
        result.extend(extra)

        if mask:
            result.extend(mask)

        return result
