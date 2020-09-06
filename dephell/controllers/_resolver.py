# built-in
import re
from logging import getLogger
from typing import TYPE_CHECKING, Optional

# external
from packaging.markers import Marker
from yaspin import yaspin

# app
from ..context_tools import nullcontext
from ..models import RootDependency
from ._conflict import analyze_conflict


if TYPE_CHECKING:
    # project
    from dephell.controllers._graph import Graph
    from dephell.controllers._mutator import Mutator


logger = getLogger('dephell.resolver')
REX_BASE_VERSION = re.compile(r'[0-9\.]+')


class Resolver:
    def __init__(self, graph: 'Graph', mutator: 'Mutator') -> None:
        self.graph = graph
        self.mutator = mutator

    def apply(self, parent, recursive: bool = False):
        """
        Returns conflicting (incompatible) dependency.
        """
        for new_dep in parent.dependencies:
            other_dep = self.graph.get(new_dep.name)
            if other_dep is None:
                # add new dep to graph
                other_dep = new_dep.copy()
                self.graph.add(other_dep)
            elif isinstance(other_dep, RootDependency):
                # if some of the dependencies cyclicaly depends on root
                # then ignore these deps
                continue
            else:
                # if dep is locked, but not used, let's just unlock it
                if other_dep.locked and not other_dep.used:
                    other_dep.unlock()
                # merge deps
                try:
                    other_dep += new_dep
                except TypeError:   # conflict happened
                    return other_dep
                # `recursive` used only in re-application of dependencies,
                # when the graph already was built before.
                if recursive:
                    self.apply(other_dep, recursive=True)
            # check
            if not other_dep.compat:
                return other_dep
        parent.applied = True

    def unapply(self, dep, *, force: bool = True, soft: bool = False) -> None:
        """
        force -- unapply deps that not applied yet
        soft -- do not mark dep as not applied.
        """
        if not force and not dep.applied:
            return
        # it must be before actual unapplying to avoid recursion on circular dependencies
        if not soft:
            dep.applied = False

        for child in dep.dependencies:
            child_name = child.name
            child = self.graph.get(child_name)
            if child is None:
                logger.debug('child not found', extra=dict(dep=dep.name, child=child_name))
                continue
            # unapply current dependency for child
            child.unapply(dep.name)
            # unapply child because he is modified
            self.unapply(child, force=False, soft=soft)

        if not soft and dep.locked:
            dep.unlock()

    def resolve(self, debug: bool = False, silent: bool = False, level: Optional[int] = None) -> bool:
        if silent:
            spinner = nullcontext(type('Mock', (), {}))
        else:
            spinner = yaspin(text='resolving...')

        with spinner as spinner:
            while True:
                resolved = self._resolve(debug=debug, silent=silent, level=level, spinner=spinner)
                if resolved is None:
                    continue
                self.graph.clear()  # remove unused deps from graph
                return resolved

    def _resolve(self, debug: bool, silent: bool, level: Optional[int], spinner) -> Optional[bool]:
        if silent:
            logger.debug('next iteration', extra=dict(
                layers=len(self.graph._layers),
                mutations=self.mutator.mutations,
            ))
        else:
            spinner.text = 'layers: {layers}, mutations: {mutations}'.format(
                layers=len(self.graph._layers),
                mutations=self.mutator.mutations,
            )
        # get not applied deps
        deps = self.graph.get_leafs(level=level)
        # if we already build deps for all nodes in graph
        if not deps:
            return True

        # check python version
        for dep in deps:
            if not dep.python_compat:
                self.graph.conflict = dep
                return False

        no_conflicts = self._apply_deps(deps, debug=debug)
        if no_conflicts:
            return None

        # if we have conflict, try to mutate graph
        groups = self.mutator.mutate(self.graph)
        # if cannot mutate
        if groups is None:
            return False
        self.graph.conflict = None
        # apply mutation
        for group in groups:
            dep = self.graph.get(group.name)
            if dep.group.number != group.number:
                logger.debug('mutated', extra=dict(
                    group_from=str(dep.group),
                    group_to=str(group),
                ))
                self.unapply(dep)
                dep.group = group
        return None

    def apply_envs(self, envs: set, deep: bool = True) -> None:
        """Filter out dependencies from the graph by the given envs.

        deep: Helps to avoid fetching dependencies (hence the network requests).
            Set it to False for not resolved graph to make filtering faster.
        """
        if not any(root.dependencies for root in self.graph.get_layer(0)):
            logger.debug('no dependencies, nothing to filter')
            return
        layer = self.graph.get_layer(1)

        # Unapply deps that we don't need
        for dep in layer:
            if not dep.applied:
                continue
            if dep.envs & envs:
                continue
            if dep.inherited_envs & envs:
                continue
            logger.debug('unapply by envs', extra=dict(dep=dep.name, envs=envs))
            # without `soft=True` all deps of this dep will be marked as unapplied
            # and ignored in Requirement.from_graph.
            # It's bad behavior because deps of this dep can be required for other
            # deps that won't be unapplied.
            if deep:
                self.unapply(dep, soft=True)
            dep.applied = False

        # Some child deps can be unapplied from other child deps, but we need them.
        # For example, if we need A, but don't need B, and A and B depends on C,
        # then C will be unapplied from B. Let's return B in the graph by reapplying A.
        for dep in self.graph:
            if not dep.applied:
                continue
            if not (dep.envs | dep.inherited_envs) & envs:
                continue
            logger.debug('reapply', extra=dict(dep=dep.name, envs=envs))
            if deep:
                self.apply(dep, recursive=True)
            dep.applied = True

    def apply_markers(self, python) -> None:
        implementation = python.implementation
        if implementation == 'python':
            implementation = 'cpython'

        # get only base part of python version because `packagings` drops
        # all markers for python prereleases
        python_version = str(python.version)
        match = REX_BASE_VERSION.match(python_version)
        if match:
            python_version = match.group()

        for dep in self.graph:
            if not dep.applied:
                continue
            if not dep.marker:
                continue

            fit = Marker(str(dep.marker)).evaluate(dict(
                python_version=python_version,
                implementation_name=implementation,
            ))
            if fit:
                continue

            self.unapply(dep, soft=True)
            dep.applied = False

    def _apply_deps(self, deps, debug: bool = False) -> bool:
        for dep in deps:
            conflict = self.apply(dep)
            if conflict is None:
                continue

            logger.debug('conflict', extra=dict(
                dep=conflict.name,
                constraint=conflict.constraint,
            ))
            self.graph.conflict = conflict.copy()

            if debug:
                print(analyze_conflict(
                    resolver=self,
                    suffix=str(self.mutator.mutations),
                ))

            # Dep can be partialy applied. Clean it.
            self.unapply(dep)
            return False

        # only if all deps applied
        return True
