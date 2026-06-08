# Trusted Publishing

MemoryX release publishing is designed for PyPI Trusted Publishing through GitHub Actions OIDC.

## Workflow

```text
GitHub Actions -> OIDC token -> PyPI trusted publisher -> package upload
```

## Required PyPI configuration

Configure the PyPI project trusted publisher with:

* owner
* repository
* workflow name: `memoryx-release-publish.yml`
* optional environment: `release`

## Safety

The workflow is `workflow_dispatch` only and requires a target:

* `testpypi`
* `pypi`
