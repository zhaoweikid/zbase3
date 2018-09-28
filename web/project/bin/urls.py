# vim: set ts=4 et sw=4 sts=4 fileencoding=utf-8 :

import index
import file

urls = (
    ('^/index', index.Index),
    ('^/upload$', file.UploadFile),
)
