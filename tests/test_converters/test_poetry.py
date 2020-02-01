# built-in
from pathlib import Path
from textwrap import dedent

# external
import pytest
import tomlkit

# project
from dephell.converters.poetry import PoetryConverter
from dephell.models import Requirement
from dephell.repositories import GitRepo


def test_load(requirements_path: Path):
    converter = PoetryConverter()
    root = converter.load(requirements_path / 'poetry.toml')
    deps = {dep.name: dep for dep in root.dependencies}
    assert 'requests' in deps
    assert 'toml' in deps
    assert 'requests[security]' in deps

    assert deps['django'].link.rev == '1.11.4'
    assert isinstance(deps['django'].repo, GitRepo)
    assert 'python_version >= "2.7.0"' in str(deps['pathlib2'].marker)

    assert deps['mysqlclient'].envs == {'main', 'mysql'}
    assert deps['pytest'].envs == {'dev'}


def test_dump(requirements_path: Path):
    converter = PoetryConverter()
    resolver = converter.load_resolver(requirements_path / 'poetry.toml')
    reqs = Requirement.from_graph(graph=resolver.graph, lock=False)
    assert len(reqs) > 2
    content = converter.dumps(reqs=reqs, project=resolver.graph.metainfo)
    assert 'requests = ' in content
    assert 'extras = ["security"]' in content
    assert 'toml = "==0.*,>=0.9.0"' in content

    assert 'https://github.com/django/django.git' in content

    parsed = tomlkit.parse(content)['tool']['poetry']
    assert '>=0.9' in parsed['dependencies']['toml']
    assert '>=2.13' in parsed['dependencies']['requests']['version']
    assert {'security'} == set(parsed['dependencies']['requests']['extras'])

    assert parsed['dependencies']['pathlib2']['allows-prereleases'] is True
    assert parsed['dependencies']['pathlib2']['python'] == '==2.7.*,>=2.7.0'

    assert parsed['dependencies']['django']['git'] == 'https://github.com/django/django.git'
    assert parsed['dependencies']['django']['rev'] == '1.11.4'

    assert 'pytest' in parsed['dev-dependencies']


def test_entrypoints(requirements_path: Path):
    converter = PoetryConverter()
    root = converter.load(requirements_path / 'poetry.toml')
    assert len(root.entrypoints) == 2

    content = converter.dumps(reqs=[], project=root)
    parsed = tomlkit.parse(content)['tool']['poetry']
    assert parsed['scripts']['my-script'] == 'my_package:main'
    assert dict(parsed['plugins']['flake8.extension']) == {'T00': 'flake8-todos.checker:Checker'}


def test_preserve_repositories():
    content = dedent("""
        [tool.poetry]
        name = "test"
        version = "1.2.3"

        [tool.poetry.dependencies]
        python = "*"

        [[tool.poetry.source]]
        name = "pypi"
        url = "https://pypi.org/pypi"
    """)
    converter = PoetryConverter()
    root = converter.loads(content)
    new_content = converter.dumps(reqs=[], project=root)
    parsed = tomlkit.parse(content)['tool']['poetry']
    new_parsed = tomlkit.parse(new_content)['tool']['poetry']
    assert parsed['source'] == new_parsed['source']
    assert parsed == new_parsed


@pytest.mark.parametrize('req', [
    'a = "*"',
    'a = "^9.5"',
    'strangE_nAm.e = ">=9.5"',
    'reponame = { git = "ssh://git@our-git-server:port/group/reponame.git", branch = "v3_2" }',
    'a = {version = "*", extras = ["nani"] }',
    'a = "*"  # god bless comments',
])
def test_preserve_reqs_format(req, temp_path: Path):
    content = dedent("""
        [tool.poetry]
        name = "test"
        version = "1.2.3"

        [tool.poetry.dependencies]
        python = "*"
        {req}
    """).format(req=req)

    converter = PoetryConverter(project_path=temp_path)
    resolver = converter.loads_resolver(content)
    reqs = Requirement.from_graph(graph=resolver.graph, lock=False)
    new_content = converter.dumps(
        reqs=reqs,
        project=resolver.graph.metainfo,
        content=content,
    )
    assert content == new_content
