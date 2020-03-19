# built-in
from argparse import ArgumentParser
from pathlib import Path

# external
import tomlkit

# app
from ..actions import make_contributing
from ..config import builders
from .base import BaseCommand


class GenerateContributingCommand(BaseCommand):
    """Create CONTRIBUTING.md for DepHell-based project.
    """
    # because we don't actually use anything from the config
    find_config = False
    file_name = 'CONTRIBUTING.md'

    @staticmethod
    def build_parser(parser) -> ArgumentParser:
        builders.build_config(parser)
        builders.build_output(parser)
        builders.build_other(parser)
        return parser

    def __call__(self) -> bool:
        if self.args.config:
            path = Path(self.args.config)
        else:
            path = Path(self.config['project']) / 'pyproject.toml'
            if not path.exists():
                self.logger.error('cannot generate file without config')
                return False

        with path.open('r', encoding='utf8') as stream:
            config = tomlkit.parse(stream.read())
        config = dict(config['tool']['dephell'])
        project_path = Path(self.config['project'])
        text = make_contributing(config=config, project_path=project_path)
        (project_path / self.file_name).write_text(text, encoding='utf8')
        self.logger.info('generated', extra=dict(file=self.file_name))
        return True
