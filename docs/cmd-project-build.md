# dephell project build

Build dist packages for the project:

1. Get dependencies from `from` parameter.
1. Make `setup.py` and `README.rst`.
1. Make [egg-info](https://setuptools.readthedocs.io/en/latest/formats.html).
1. Make sdist (archived project source code and egg-info).
1. Make [wheel](https://pythonwheels.com/).

After all you can use [twine](https://github.com/pypa/twine/) to upload it on PyPI.

## Example

```bash
$ dephell project build --from pyproject.toml
$ twine upload dist/*
```

## See also

1. [dephell deps convert](cmd-deps-convert) for details how DepHell converts dependencies from one format to another.
1. [dephell project bump](cmd-project-bump) to bump project version.
1. [dephell project upload](cmd-project-upload) to upload dist packages (on PyPI or somewhere else).
1. [dephell project test](cmd-project-test) to see how the project behaves on a clean installation.
1. [Full list of config parameters](params)
