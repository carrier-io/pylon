# pylon

Plugin based galloper core

To run pylon `PYLON_CONFIG_SEED` (or legacy `CORE_CONFIG_SEED`) needs to be specified in env
in format `file:/path/to/config.yml`

### Example command to build arm image:
`docker buildx build --platform linux/arm64 -f "Dockerfile" -t "pylon:local" .`

### Build command for latest pylon (add --push to push)
`docker buildx build --platform linux/amd64,linux/arm64 -t getcarrier/pylon:latest .`

### Q&A

In case of error running pylon in venv

```
INFO - pylon.core.tools.process - ERROR: Can not perform a '--user' install. User site-packages are not visible in this virtualenv.
```

in pyvenv.conf set `include-system-site-packages = true`
