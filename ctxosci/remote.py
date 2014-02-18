class FakeExecutor(object):
    def __init__(self):
        self.executed_commands = []

    def run(self, args):
        self.executed_commands.append(args)
