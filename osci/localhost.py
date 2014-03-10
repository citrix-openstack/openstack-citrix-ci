class Localhost(object):
    def commands_to_extract_stdout_tgz_to(self, target):
        return 'tar -xzf - -C {0}'.format(target).split()
