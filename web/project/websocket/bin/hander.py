from zbase3.web.websocketcore import WebSocketHandler


class EchoApplication(WebSocketHandler):
    def on_open(self):
        print("Connection opened")

    def on_message(self, message):
        return message

    def on_close(self, reason):
        self.ws.close()