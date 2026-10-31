# Package boundaries

The repository ships two independently installable Python distributions:

- `mcp-runtime-sentinel` is the runtime wheel. It contains `sentinel/` modules
  needed by the HTTP gateway, configured policy, audit, state, and serving CLI.
- `mcp-runtime-sentinel-research` is installed from `research/`. It contains
  synthetic fixtures, experiments, publication analysis, plots, the dashboard,
  and the test mock MCP server. It depends on the runtime distribution.

The runtime package does not import `sentinel_research`. Research commands use
`python -m sentinel_research.cli`; runtime commands use `python -m sentinel.cli`.
The runtime wheel isolation check is `python scripts/check_runtime_wheel.py`.

From a checkout, install both packages to run the full test suite:

```sh
python -m pip install -e '.[dev]' -e 'research[dev]'
python -m pytest
python -m unittest discover -s tests
```

Install `research[paper]` when running the optional paper-rendering script that
uses Matplotlib. The main runtime package has no Matplotlib dependency.
