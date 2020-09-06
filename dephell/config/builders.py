# built-in
from pathlib import Path

# external
from dephell_argparse._parser import Parser
from dephell_versioning import get_schemes

# app
from ..constants import FORMATS, LOG_FORMATTERS, LOG_LEVELS, REPOSITORIES, STRATEGIES


# helper function for path values
def expanded_path(string):
    return Path(string).expanduser().resolve().as_posix()


env_help = (
    'Pipenv has 2 envs in same file: main and dev. '
    'For poetry you can also use main-opt and dev-opt '
    'that indicates to install optional requirements '
    'from given env.'
)


def build_config(parser: Parser) -> None:
    config_group = parser.add_argument_group('Configuration file')
    config_group.add_argument('-c', '--config', help='path to config file.', type=expanded_path)
    config_group.add_argument('-e', '--env', help='environment in config.')


def build_from(parser: Parser) -> None:
    from_group = parser.add_argument_group('Input file')
    from_group.add_argument('--from', help='path or format for reading requirements.', type=expanded_path)
    from_group.add_argument('--from-format', choices=FORMATS, help='format for reading requirements.')
    from_group.add_argument('--from-path', help='path to input file.', type=expanded_path)


def build_to(parser) -> None:
    to_group = parser.add_argument_group('Output file')
    to_group.add_argument('--to', help='path or format for writing requirements.', type=expanded_path)
    to_group.add_argument('--to-format', choices=FORMATS, help='output requirements file format.')
    to_group.add_argument('--to-path', help='path to output file.', type=expanded_path)
    to_group.add_argument(
        '--sdist-ratio',
        help='ratio of tests and project size after which tests will be excluded from sdist.',
    )


def build_resolver(parser: Parser) -> None:
    resolver_group = parser.add_argument_group('Resolver rules')
    resolver_group.add_argument('--strategy', choices=STRATEGIES, help='Algorithm to select best release.')
    resolver_group.add_argument('--prereleases', action='store_true', help='Allow prereleases')
    resolver_group.add_argument('--mutations', type=int, help='Maximum mutations limit')


def build_api(parser: Parser) -> None:
    api_group = parser.add_argument_group('APIs endpoints')
    api_group.add_argument('--warehouse', nargs='*', help='warehouse API URL.')
    api_group.add_argument('--bitbucket', help='bitbucket API URL.')
    api_group.add_argument('--repo', choices=REPOSITORIES, help='force repository for first-level deps.')


def build_output(parser: Parser) -> None:
    output_group = parser.add_argument_group('Console output')
    output_group.add_argument('--format', choices=LOG_FORMATTERS, help='output format.')
    output_group.add_argument('--level', choices=LOG_LEVELS, help='minimal level for log messages.')

    output_group.add_argument('--nocolors', action='store_true', help='do not color output.')
    output_group.add_argument('--table', action='store_true', help='use table for output.')
    output_group.add_argument('--silent', action='store_true', help='suppress any output except errors.')
    output_group.add_argument('--filter', help='filter for JSON output.')

    output_group.add_argument('--traceback', action='store_true', help='show traceback for exceptions.')
    output_group.add_argument('--pdb', action='store_true', help='run pdb for critical exceptions.')


def build_venv(parser: Parser) -> None:
    venv_group = parser.add_argument_group('Virtual environment')
    venv_group.add_argument('--venv', help='path to venv directory for project.', type=expanded_path)
    venv_group.add_argument('--python', help='python version for venv.')
    venv_group.add_argument('--dotenv', help='path to .env file', type=expanded_path)


def build_docker(parser):
    docker_group = parser.add_argument_group('Docker container')
    docker_group.add_argument('--docker-repo', help='image name without tag')
    docker_group.add_argument('--docker-tag', help='image tag')
    docker_group.add_argument('--docker-container', help='container name')


def build_other(parser: Parser) -> None:
    other_group = parser.add_argument_group('Other')

    other_group.add_argument('--cache-path', help='path to dephell cache', type=expanded_path)
    other_group.add_argument('--cache-ttl', type=int, help='Time to live for releases list cache')

    other_group.add_argument('--project', help='path to the current project', type=expanded_path)
    other_group.add_argument('--bin', help='path to the dir for installing scripts', type=expanded_path)
    other_group.add_argument('--ca', help='path to CA_BUNDLE file for SSL verification.', type=expanded_path)

    other_group.add_argument('--envs', nargs='*', help='environments (main, dev) or extras to install')
    other_group.add_argument('--tests', nargs='*', help='paths to test files', type=expanded_path)
    other_group.add_argument('--versioning', choices=sorted(get_schemes()),
                             help='versioning scheme for project')
