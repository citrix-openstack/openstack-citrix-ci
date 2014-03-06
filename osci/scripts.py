import sys
import argparse
import logging
from osci import commands


def get_parser_for(command):
    parser = argparse.ArgumentParser()
    for parameter in command.parameters():
        parser.add_argument(parameter)

    return parser


def run_command(cmd_class):
    setup_logging()
    parser = get_parser_for(cmd_class)
    env = parser.parse_args()
    command = cmd_class(vars(env))
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
    sys.exit(run_command(commands.WatchGerrit))

def create_dbschema():
    sys.exit(run_command(commands.CreateDBSchema))