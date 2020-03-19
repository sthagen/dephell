"""Actions are functions that used only in commands
"""

# app
from ._autocomplete import make_bash_autocomplete, make_zsh_autocomplete
from ._contributing import make_contributing
from ._converting import attach_deps
from ._docker import get_docker_container
from ._dotenv import read_dotenv
from ._downloads import get_downloads_by_category, get_total_downloads
from ._editorconfig import make_editorconfig
from ._entrypoints import get_entrypoints
from ._git import git_commit, git_tag
from ._install import install_dep, install_deps
from ._json import make_json
from ._package import get_package, get_packages, get_resolver
from ._python import get_lib_path, get_python, get_python_env
from ._shutil import format_size, get_path_size
from ._transform import transform_imports
from ._travis import make_travis
from ._venv import get_venv


__all__ = [
    'attach_deps',
    'format_size',
    'get_docker_container',
    'get_downloads_by_category',
    'get_entrypoints',
    'get_lib_path',
    'get_package',
    'get_packages',
    'get_path_size',
    'get_python_env',
    'get_python',
    'get_resolver',
    'get_total_downloads',
    'get_venv',
    'git_commit',
    'git_tag',
    'install_dep',
    'install_deps',
    'make_bash_autocomplete',
    'make_contributing',
    'make_editorconfig',
    'make_json',
    'make_travis',
    'make_zsh_autocomplete',
    'read_dotenv',
    'transform_imports',
]
