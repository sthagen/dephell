# built-in
from pathlib import Path

# external
import pytest
from dephell_discover import Root as PackageRoot

# project
from dephell.commands import VendorImportCommand
from dephell.config import Config
from dephell.constants import IS_WINDOWS
from dephell.controllers import Graph, Mutator, Resolver
from dephell.models import RootDependency


@pytest.mark.skipif(IS_WINDOWS, reason='unsupported on windows')
def test_patch_imports(temp_path: Path):
    (temp_path / 'project').mkdir()
    (temp_path / 'project' / '__init__.py').write_text('import requests\nimport django')
    (temp_path / 'project' / 'vendor' / 'requests').mkdir(parents=True)
    (temp_path / 'project' / 'vendor' / 'requests' / '__init__.py').touch()

    config = Config()
    config.attach(dict(project=str(temp_path)))
    package = PackageRoot(name='project', path=temp_path)
    root = RootDependency(raw_name='project', package=package)
    resolver = Resolver(
        graph=Graph(root),
        mutator=Mutator(),
    )
    command = VendorImportCommand(argv=[], config=config)
    command._patch_imports(
        resolver=resolver,
        output_path=temp_path / 'project' / 'vendor',
    )

    expected = 'import project.vendor.requests as requests\nimport django'
    assert (temp_path / 'project' / '__init__.py').read_text() == expected
