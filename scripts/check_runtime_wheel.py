"""Fail if the runtime wheel contains research code or imports it."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import zipfile


def main() -> None:
    wheels = sorted(Path("dist").glob("mcp_runtime_sentinel-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one runtime wheel in dist/, found {len(wheels)}")
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        packages = {name.split("/", 1)[0] for name in names if ".dist-info/" not in name}
        if packages != {"sentinel"}:
            raise SystemExit(f"runtime wheel contains unexpected top-level packages: {packages}")
        modules = [name for name in names if name.startswith("sentinel/") and name.endswith(".py")]
        if not modules:
            raise SystemExit("runtime wheel contains no Python modules")
        for name in modules:
            tree = ast.parse(archive.read(name).decode("utf-8"), filename=name)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(alias.name == "sentinel_research" or alias.name.startswith("sentinel_research.") for alias in node.names):
                        raise SystemExit(f"runtime wheel imports research package: {name}:{node.lineno}")
                elif isinstance(node, ast.ImportFrom) and node.module and (
                    node.module == "sentinel_research" or node.module.startswith("sentinel_research.")
                ):
                    raise SystemExit(f"runtime wheel imports research package: {name}:{node.lineno}")
    sys.path.insert(0, str(wheel.resolve()))
    import sentinel

    if sentinel.__name__ != "sentinel":
        raise SystemExit("runtime wheel import resolved the wrong package")
    if importlib.util.find_spec("sentinel_research") is not None:
        raise SystemExit("runtime wheel environment unexpectedly resolves sentinel_research")
    print(f"runtime wheel isolation passed: {wheel.name}; {len(modules)} runtime modules; no research package/imports")


if __name__ == "__main__":
    main()
