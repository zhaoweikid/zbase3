import ping
import hander

urls = (
    ('/ping', ping.Ping),
    ('/v1/msg/connect', hander.EchoApplication),
)