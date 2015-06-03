import tempfile
import shutil
import os


class FakeFilesystem(object):
    def __init__(self):
        self.contents = {}

    def mkdtemp(self, suffix):
        path = 'RANDOMPATH-{0}'.format(suffix)
        assert path not in self.contents, ""
        self.contents[path] = []
        return path

    def rmtree(self, path):
        assert path in self.contents, "rmtree non existing {0}".format(path)
        del self.contents[path]

    def mkdir(self, path):
        assert path not in self.contents, "mkdir already existing {0}".format(path)
        parent_path = os.path.dirname(path)
        assert parent_path in self.contents, "mkdir parent not existing {0}".format(parent_path)
        self.contents[parent_path].append(path)


class RealFilesystem(object):
    def mkdtemp(self, suffix):
        return tempfile.mkdtemp(suffix=suffix)

    def rmtree(self, path):
        shutil.rmtree(path)

    def mkdir(self, path):
        os.mkdir(path)




