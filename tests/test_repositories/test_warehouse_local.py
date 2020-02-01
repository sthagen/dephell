# built-in
import asyncio

# project
from dephell.controllers import DependencyMaker
from dephell.models import RootDependency
from dephell.repositories import WarehouseLocalRepo


loop = asyncio.get_event_loop()


def test_get_releases(repository_path):
    repo = WarehouseLocalRepo(name='pypi', path=repository_path)
    root = RootDependency()
    dep = DependencyMaker.from_requirement(source=root, req='dephell-discover')[0]
    releases = repo.get_releases(dep=dep)
    releases = {str(r.version): r for r in releases}
    assert set(releases) == {'0.2.4', '0.2.5'}


def test_get_dependencies(repository_path):
    repo = WarehouseLocalRepo(name='pypi', path=repository_path)

    coroutine = repo.get_dependencies(name='dephell-discover', version='0.2.4')
    deps = loop.run_until_complete(asyncio.gather(coroutine))[0]
    deps = {dep.name: dep for dep in deps}
    assert set(deps) == {'attrs'}
