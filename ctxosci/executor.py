import subprocess
import logging


log = logging.getLogger(__name__)

def create_executor(name):
    if name in EXECUTOR_NAMES:
        return EXECUTOR_NAMES[name]()
    return FakeExecutor()


class PrintExecutor(object):
    def run(self, args):
        print ' '.join(args)

    def pipe_run(self, args1, args2):
        print ' '.join(args1 + ['|'] + args2)


class FakeExecutor(object):
    def __init__(self):
        self.executed_commands = []

    def run(self, args):
        self.executed_commands.append(args)

    def pipe_run(self, args1, args2):
        self.executed_commands.append(fake_pipe(args1, args2))


class RealExecutor(object):
    def run(self, args):
        log.info('Executing %s', args)
        return subprocess.call(args)

    def pipe_run(self, args1, args2):
        log.info('Pipe the output of %s to %s', args1, args2)
        proc1 = subprocess.Popen(
            args1, stdout=subprocess.PIPE)
        proc2 = subprocess.Popen(args2, stdin=proc1.stdout)
        proc1.stdout.close()
        proc2.communicate()
        proc1.wait()
        log.info('Producer returned %s', proc1.returncode)
        log.info('Consumer returned %s', proc2.returncode)


def escaped(args):
    return [arg.replace('*', '\\*') for arg in args]


def fake_pipe(args1, args2):
    return [args1, '|', args2]


EXECUTOR_NAMES = {
    'print': PrintExecutor,
    'exec': RealExecutor,
}
