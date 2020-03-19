# built-in
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path

# app
from ..actions import make_json
from ..config import builders
from .base import BaseCommand


class JailListCommand(BaseCommand):
    """Show all jails and their entrypoints.
    """
    find_config = False

    @staticmethod
    def build_parser(parser) -> ArgumentParser:
        builders.build_config(parser)
        builders.build_venv(parser)
        builders.build_output(parser)
        builders.build_other(parser)
        return parser

    def __call__(self) -> bool:
        venvs_path = self.config['venv'].replace('-{digest}', '')
        venvs_path = venvs_path.format(project='*', digest='', env='')
        venvs_path = str(Path(venvs_path).resolve())

        entrypoints = defaultdict(list)
        for entrypoint in Path(self.config['bin']).iterdir():
            if not entrypoint.exists():
                continue  # jail disappeared on disk
            venv_path = entrypoint.resolve().parent.parent
            if venv_path.match(venvs_path):
                entrypoints[venv_path.name].append(entrypoint.name)

        print(make_json(
            data=dict(entrypoints),
            key=self.config.get('filter'),
            colors=not self.config['nocolors'],
            table=self.config['table'],
            sep=None,
        ))
        return True
