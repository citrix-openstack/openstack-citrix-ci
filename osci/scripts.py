import sys
import argparse
import logging
from osci import commands
from osci import config


def get_parser_for(command):
    parser = argparse.ArgumentParser()
    for parameter in command.parameters():
        parser.add_argument(parameter)

    return parser


def run_command(cmd_class, env=None):
    setup_logging()
    if env is None:
        parser = get_parser_for(cmd_class)
        env = vars(parser.parse_args())
    command = cmd_class(env)
    return command()


def setup_logging():
    logging.basicConfig(level=logging.DEBUG)


def cp_dom0_logserver():
    sys.exit(run_command(commands.GetDom0Logs))


def check_connection():
    sys.exit(run_command(commands.CheckConnection))


def run_tests():
    sys.exit(run_command(commands.RunTests))


def watch_gerrit():
    c = config.Configuration()
    env = dict(
        gerrit_client='pygerrit',
        gerrit_host=c.get('GERRIT_HOST'),
        event_target='queue',
        gerrit_port=c.get('GERRIT_PORT'),
        gerrit_username=c.get('GERRIT_USERNAME'),
        dburl=c.get('DATABASE_URL'),
        comment_re=c.get('RECHECK_REGEXP'),
        projects=c.get('PROJECT_CONFIG'),
    )
    sys.exit(run_command(commands.WatchGerrit, env=env))

def create_dbschema():
    env = dict(
        dburl=config.Configuration().get('DATABASE_URL')
    )
    sys.exit(run_command(commands.CreateDBSchema, env=env))