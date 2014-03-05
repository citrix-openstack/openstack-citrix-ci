import tempfile
import shutil


class FakeFilesystem(object):
    def __init__(self):
        self.contents = {}
        self.counter = 1

    def mkdtemp(self, suffix):
        path = 'RANDOMPATH-{0}'.format(suffix)
        self.contents[path] = ""
        return path

    def rmtree(self, path):
        assert path in self.contents, "rmtree non existing {0}".format(path)
        del self.contents[path]


class RealFilesystem(object):
    def mkdtemp(self, suffix):
        return tempfile.mkdtemp(suffix=suffix)

    def rmtree(self, path):
        shutil.rmtree(path)




