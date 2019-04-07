# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

urls = (
    ('^/ping$', "ping.Ping"),
    ('^/index$', "index.Index"),
    ('^/upload$', "file.UploadFile"),
    ('^/api1$', "index.MyAPI1"),
    ('^/api2/(login|logout|now|today|myerror)$', "index.MyAPI2"),
)
