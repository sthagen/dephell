# built-in
import subprocess
from argparse import ArgumentParser
from pathlib import Path

# app
from ..config import builders
from .base import BaseCommand


class GenerateAuthorsCommand(BaseCommand):
    """Create AUTHORS file for project by git log.
    """
    # because we don't actually use anything from the config
    find_config = False

    @staticmethod
    def build_parser(parser) -> ArgumentParser:
        builders.build_config(parser)
        builders.build_output(parser)
        builders.build_other(parser)
        return parser

    def __call__(self) -> bool:
        result = subprocess.run(
            ['git', 'log', '--pretty="%ae|%an%n%ce|%cn"'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        authors = dict()
        for line in result.stdout.decode().strip().split('\n'):
            mail, name = line.split('|')
            mail = mail.strip().replace('"', '')
            name = name.strip().replace('"', '')
            authors[mail] = name
        lines = ('{} <{}>'.format(name, mail) for mail, name in authors.items())
        Path('AUTHORS').write_text('\n'.join(sorted(lines)), encoding='utf-8')
        self.logger.info('AUTHORS generated')
        return True
