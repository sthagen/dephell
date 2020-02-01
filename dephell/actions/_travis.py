# built-in
from typing import Any, Dict, Optional


HEADER = """
# Config for Travis CI, tests powered by DepHell.
# https://travis-ci.org/
# https://github.com/dephell/dephell

language: python
dist: xenial

before_install:
  # show a little bit more information about environment
  - sudo apt-get install -y tree
  - env
  - tree
  # install DepHell
  # https://github.com/travis-ci/travis-ci/issues/8589
  - curl -L dephell.org/install | /opt/python/3.7/bin/python
  - dephell inspect self
install:
  - dephell venv create --env=$ENV --python="/opt/python/$TRAVIS_PYTHON_VERSION/bin/python"
  - dephell deps install --env=$ENV
script:
  - dephell venv run --env=$ENV

matrix:
"""

PYTEST = """
    - python: "3.6.7"
      env: ENV={env}
    - python: "3.7"
      env: ENV={env}
    - python: "3.8"
      env: ENV={env}
    - python: "pypy3.6"
      env: ENV={env}

    - os: osx
      language: generic
      env: ENV={env}
      before_install:
        - curl https://raw.githubusercontent.com/dephell/dephell/master/install.py | /usr/local/bin/python3
        - dephell inspect self
      install:
        - dephell venv create --env=$ENV --python=/usr/local/bin/python3 --level=DEBUG --traceback
        - dephell deps install --env=$ENV --level=DEBUG --traceback
"""

OTHER = """
    - python: "3.7"
      env: ENV={env}
"""

LOCKFILE = """
  allow_failures:
    - name: security
    - name: outdated
    - python: "3.8-dev"

  include:
    - name: security
      install:
        - "true"
      script:
        - dephell deps audit
    - name: outdated
      install:
        - "true"
      script:
        - dephell deps outdated
"""


def make_travis(config: Dict[str, Dict[str, Any]]) -> Optional[str]:
    content = HEADER.strip()
    locked = 'lock' in config.get('main', {}).get('to', {}).get('format', '')
    content += LOCKFILE if locked else '\n  include:\n'

    tested = False
    for env, section in config.items():
        if 'command' not in section:
            continue
        if 'from' not in section and 'to' not in section:
            continue
        if 'pypy' in section.get('python', ''):
            continue

        executable = section['command'].split()[0]
        if executable in ('sphinx-build', 'twine'):
            continue

        if executable == 'pytest':
            content += PYTEST.format(env=env)
        else:
            content += OTHER.format(env=env)
        tested = True

    if not locked and not tested:
        return None

    return content
