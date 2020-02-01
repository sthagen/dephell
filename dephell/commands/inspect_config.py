# built-in
from argparse import ArgumentParser

# app
from ..actions import make_json
from ..config import builders
from .base import BaseCommand


class InspectConfigCommand(BaseCommand):
    """Show current config.
    """
    @staticmethod
    def build_parser(parser) -> ArgumentParser:
        builders.build_config(parser)
        builders.build_from(parser)
        builders.build_to(parser)
        builders.build_resolver(parser)
        builders.build_api(parser)
        builders.build_venv(parser)
        builders.build_output(parser)
        builders.build_other(parser)
        return parser

    def __call__(self) -> bool:
        config = self.config._data.copy()
        del config['auth']  # do not show credentials
        print(make_json(
            data=config,
            key=self.config.get('filter'),
            colors=not self.config['nocolors'],
            table=self.config['table'],
        ))
        return True
