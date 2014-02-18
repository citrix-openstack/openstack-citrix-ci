import subprocess


def create_executor(name):
    if name in EXECUTOR_NAMES:
        return EXECUTOR_NAMES[name]()
    return FakeExecutor()


class PrintExecutor(object):
    def run(self, args):
        print ' '.join(args)


class FakeExecutor(object):
    def __init__(self):
        self.executed_commands = []

    def run(self, args):
        self.executed_commands.append(args)


class RealExecutor(object):
    def run(self, args):
        subprocess.call(args)


def escaped(args):
    return [arg.replace('*', '\\*') for arg in args]


EXECUTOR_NAMES = {
    'print': PrintExecutor,
    'exec': RealExecutor,
}
