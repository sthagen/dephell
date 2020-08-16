# built-in
from collections import defaultdict
from pathlib import Path
from typing import List, Optional, Tuple, Union

# external
import attr
import tomlkit
from dephell_discover import Root as PackageRoot
from dephell_specifier import RangeSpecifier
from packaging.utils import canonicalize_name
from tomlkit.items import InlineTable, String, Table

# app
from ..controllers import DependencyMaker, Readme, RepositoriesRegistry
from ..models import Author, Constraint, Dependency, EntryPoint, Requirement, RootDependency
from ..repositories import WarehouseLocalRepo
from .base import BaseConverter


@attr.s()
class PoetryConverter(BaseConverter):
    lock = attr.ib(type=bool, default=False)

    fields = (
        'version', 'python', 'platform', 'allows-prereleases',
        'optional', 'extras', 'develop',
        'git', 'branch', 'tag', 'rev',
        'file', 'path',
    )
    _metafields = ('version', 'description', 'license', 'keywords', 'classifiers')

    def can_parse(self, path: Path, content: Optional[str] = None) -> bool:
        if isinstance(path, str):
            path = Path(path)
        if content:
            return '[tool.poetry]' in content or '[tool.poetry.' in content
        return path.name in ('poetry.toml', 'pyproject.toml')

    def loads(self, content) -> RootDependency:
        doc = tomlkit.parse(content)
        if 'tool' not in doc:
            doc['tool'] = {'poetry': tomlkit.table()}
        elif 'poetry' not in doc['tool']:
            doc['tool']['poetry'] = tomlkit.table()
        section = doc['tool']['poetry']
        root = RootDependency(
            package=PackageRoot(path=self.project_path or Path()),
        )

        # read metainfo
        if 'name' in section:
            root.raw_name = section['name']
        for field in self._metafields:
            if field in section:
                value = section[field]
                if isinstance(value, list):
                    value = tuple(value)
                setattr(root, field, value)
        if 'authors' in section:
            root.authors = tuple(Author.parse(str(author)) for author in section['authors'])
        if 'readme' in section:
            path = Path(section['readme'])
            if path.exists():
                root.readme = Readme(path=path)

        # read links
        for field in ('homepage', 'repository', 'documentation'):
            if field in section:
                root.links[field] = section[field]

        # read entrypoints
        root.entrypoints = []
        for name, content in section.get('scripts', {}).items():
            if isinstance(content, str):
                entrypoint = EntryPoint(name=name, path=content)
            else:
                entrypoint = EntryPoint(
                    name=name,
                    path=content['callable'],
                    extras=content['extras'],
                )
            root.entrypoints.append(entrypoint)
        for group_name, group_content in section.get('plugins', {}).items():
            for name, path in sorted(group_content.items()):
                root.entrypoints.append(EntryPoint(name=name, path=path, group=group_name))
        root.entrypoints = tuple(root.entrypoints)

        # update repository
        root.repo = RepositoriesRegistry()
        if section.get('source'):
            for source in section['source']:
                root.repo.add_repo(url=source['url'], name=source['name'])
        root.repo.attach_config()

        # get envs for deps
        envs = defaultdict(set)
        for extra, deps in section.get('extras', {}).items():
            for dep in deps:
                envs[dep].add(extra)
        for dep in section.get('dependencies', {}):
            envs[dep].add('main')
        for dep in section.get('dev-dependencies', {}):
            envs[dep].add('dev')

        # read dependencies
        deps = []
        for section_name in ('dependencies', 'dev-dependencies'):
            for name, content in section.get(section_name, {}).items():
                if name == 'python' and section_name == 'dependencies':
                    root.python = RangeSpecifier(content)
                    continue
                deps.extend(self._make_deps(
                    root=root,
                    name=name,
                    content=content,
                    envs=envs.get(name),
                ))

        root.attach_dependencies(deps)
        return root

    def dumps(self, reqs, project: RootDependency, content=None) -> str:
        if content:
            doc = tomlkit.parse(content)
        else:
            doc = tomlkit.document()
        if 'tool' not in doc:
            doc['tool'] = {'poetry': tomlkit.table()}
        elif 'poetry' not in doc['tool']:
            doc['tool']['poetry'] = tomlkit.table()
        section = doc['tool']['poetry']

        # metainfo
        section['name'] = project.raw_name
        for field in self._metafields:
            value = getattr(project, field)
            if isinstance(value, tuple):
                value = list(value)
            if not value:   # delete
                if field in section:
                    del section[field]
            elif field not in section:  # insert
                section[field] = value
            elif section[field].value != value:  # update
                section[field] = value

        # write links
        for name in ('homepage', 'repository', 'documentation'):
            if name in project.links:
                section[name] = project.links[name]

        if project.authors:
            section['authors'] = [str(author) for author in project.authors]
        elif 'authors' in section:
            del section['authors']

        if project.readme:
            section['readme'] = project.readme.path.name
        elif 'readme' in section:
            del section['readme']

        self._add_entrypoints(section=section, entrypoints=project.entrypoints)

        # dependencies
        names_mapping = dict()
        for section_name, is_dev in [('dependencies', False), ('dev-dependencies', True)]:
            if section_name not in section:
                section[section_name] = tomlkit.table()
                continue

            # clean file from outdated dependencies
            names = {req.name for req in reqs if is_dev is req.is_dev} | {'python'}
            for name in dict(section[section_name]):
                normalized_name = canonicalize_name(name)
                names_mapping[normalized_name] = name
                if normalized_name not in names:
                    del section[section_name][name]

        # python version
        if section['dependencies'].get('python', '') != (project.python or '*'):
            section['dependencies']['python'] = str(project.python) or '*'

        # write dependencies
        for section_name, is_dev in [('dependencies', False), ('dev-dependencies', True)]:
            for req in reqs:
                if is_dev is not req.is_dev:
                    continue
                raw_name = names_mapping.get(req.name, req.raw_name)
                old_spec = section[section_name].get(raw_name)

                # do not overwrite dep if nothing is changed
                if old_spec:
                    old_dep = self._make_deps(
                        root=RootDependency(),
                        name=raw_name,
                        content=old_spec,
                        envs={'main'},
                    )[0]
                    if req.same_dep(old_dep):
                        continue

                # overwrite
                section[section_name][raw_name] = self._format_req(req=req)

            # remove empty section
            if not section[section_name].value:
                del section[section_name]

        # extras
        extras = defaultdict(list)
        for req in reqs:
            if req.is_main:
                for extra in req.main_envs:
                    extras[extra].append(req.name)
            if req.is_dev:
                for extra in req.dev_envs:
                    extras[extra].append(req.name)
        if extras:
            if 'extras' in section:
                # drop old extras
                for extra in section['extras']:
                    if extra not in extras:
                        del section['extras'][extra]
            else:
                # create section if doesn't exist
                section['extras'] = tomlkit.table()
            # add new extras
            for extra, deps in extras.items():
                if list(section['extras'].get(extra, [])) == deps:
                    continue
                section['extras'][extra] = deps
        elif 'extras' in section:
            # deop all old extras if there are no new extras
            del section['extras']

        if not project.dependencies:
            project.attach_dependencies([req.dep for req in reqs])
        self._add_repositories(section=section, root=project)
        return tomlkit.dumps(doc).rstrip() + '\n'

    @staticmethod
    def _add_entrypoints(section: Table, entrypoints: Tuple[EntryPoint, ...]) -> None:
        # drop old console_scripts
        if 'scripts' in section:
            scripts = {e.name for e in entrypoints if e.group == 'console_scripts'}
            for script_name in list(section['scripts']):
                if script_name not in scripts:
                    del section['scripts'][script_name]

        # add console_scripts
        for entrypoint in entrypoints:
            if entrypoint.group != 'console_scripts':
                continue
            if 'scripts' not in section:
                section['scripts'] = tomlkit.table()
            if entrypoint.extras:
                content = tomlkit.inline_table()
                content['callable'] = entrypoint.path
                content['extras'] = entrypoint.extras
            else:
                content = entrypoint.path
            section['scripts'][entrypoint.name] = content

        # drop old plugins
        if 'plugins' in section:
            groups = defaultdict(set)
            for entrypoint in entrypoints:
                if entrypoint.group != 'console_scripts':
                    groups[entrypoint.group].add(entrypoint.name)
            for group_name, group_content in section['plugins'].items():
                if group_name not in groups:
                    del section['plugins'][group_name]
                    continue
                for script_name in group_content:
                    if script_name not in groups[group_name]:
                        del section['plugins'][group_name][script_name]

        # add plugins
        for entrypoint in entrypoints:
            if entrypoint.group == 'console_scripts':
                continue
            if 'plugins' not in section:
                section['plugins'] = tomlkit.table()
            if entrypoint.group not in section['plugins']:
                section['plugins'][entrypoint.group] = tomlkit.table()
            section['plugins'][entrypoint.group][entrypoint.name] = entrypoint.path

    @staticmethod
    def _add_repositories(section, root: RootDependency):
        # get repositories
        urls = dict()
        for repo in root.warehouses:
            if isinstance(repo, WarehouseLocalRepo):
                continue
            urls[repo.name] = repo.pretty_url

        # remove or update old repositories
        added = []
        sources = tomlkit.aot()
        if section.get('source'):
            if hasattr(section, 'item'):
                old_sources = section.item('source')
            else:
                old_sources = section['source']
            for source in old_sources:
                if source['name'] in urls:
                    if source['url'] != urls[source['name']]:
                        source['url'] = urls[source['name']]
                    sources.append(source)
                    added.append(source['name'])

        # add new repositories
        for name, url in sorted(urls.items()):
            if name not in added:
                source = tomlkit.table()
                source['name'] = name
                source['url'] = url
                sources.append(source)

        section['source'] = sources

        # remove section if empty
        if not section['source']:
            del section['source']

    # https://github.com/sdispater/tomlkit/blob/master/pyproject.toml
    def _make_deps(self, root, name: str, content, envs: set) -> List[Dependency]:
        if isinstance(content, str):
            deps = [Dependency(
                raw_name=name,
                constraint=Constraint(root, content),
                repo=root.repo,
                envs=envs,
            )]
            return deps

        # get link
        url = content.get('file') or content.get('path')
        if url and not url.startswith('http'):
            url = str(self._make_dependency_path_absolute(Path(url)))
        if not url and 'git' in content:
            url = 'git+' + content['git']
        rev = content.get('rev') or content.get('branch') or content.get('tag')
        if rev:
            url += '@' + rev

        # make marker
        markers = []
        # https://www.python.org/dev/peps/pep-0496/
        if 'platform' in content:
            markers.append('sys_platform == "{}" '.format(content['platform']))
        if 'python' in content:
            markers.append(RangeSpecifier(content['python']).to_marker('python_version'))
        markers = ' and '.join(markers)

        # poetry plans to remove the allows-prereleases key,
        # and will only use the allow-prereleases key instead.
        is_prereleases = content.get('allows-prereleases', False) or content.get('allow-prereleases', False)

        deps = DependencyMaker.from_params(
            raw_name=name,
            constraint=Constraint(root, content.get('version', '')),
            source=root,
            extras=set(content.get('extras', [])),
            marker=markers or None,
            url=url,
            editable=content.get('develop', False),
            envs=envs,
            prereleases=is_prereleases,
        )
        return deps

    def _format_req(self, req: Requirement) -> Union[InlineTable, String]:
        result = tomlkit.inline_table()
        for name, value in req:
            if name in self.fields:
                if isinstance(value, tuple):
                    value = list(value)
                result[name] = value
        if req.prereleases:
            result['allows-prereleases'] = True
        if 'version' not in result and 'git' not in result:
            result['version'] = '*'
        # if we have only version, return string instead of table
        if tuple(result.value) == ('version', ):
            return result['version']

        return result
