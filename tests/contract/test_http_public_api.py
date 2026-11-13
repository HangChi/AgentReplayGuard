"""HTTP 传输层适配器的公开契约与可选依赖隔离。"""

from __future__ import annotations

import inspect
import subprocess
import sys

import httpx

from agentreplayguard.adapters.httpx import (
    AsyncFaultyTransport,
    FaultyTransport,
    HttpEffect,
)


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )


def test_public_symbols_are_importable():
    assert HttpEffect.__name__ == "HttpEffect"
    assert issubclass(FaultyTransport, httpx.BaseTransport)
    assert issubclass(AsyncFaultyTransport, httpx.AsyncBaseTransport)


def test_transport_signatures_match_contract():
    sync_params = list(inspect.signature(FaultyTransport.__init__).parameters)
    assert sync_params == ["self", "base", "scenario", "classify"]

    async_params = list(inspect.signature(AsyncFaultyTransport.__init__).parameters)
    assert async_params == ["self", "base", "scenario", "classify"]

    assert inspect.iscoroutinefunction(AsyncFaultyTransport.handle_async_request)
    assert inspect.iscoroutinefunction(AsyncFaultyTransport.aclose)
    assert not inspect.iscoroutinefunction(FaultyTransport.handle_request)


def test_core_package_import_does_not_load_http_adapter():
    code = (
        "import sys\n"
        "import agentreplayguard\n"
        "assert 'agentreplayguard.adapters.httpx' not in sys.modules\n"
        "print('ok')\n"
    )
    result = _run_python(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_missing_httpx_gives_actionable_import_error():
    code = (
        "import sys\n"
        "class Blocker:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname == 'httpx' or fullname.startswith('httpx.'):\n"
        "            raise ModuleNotFoundError(\"No module named 'httpx'\")\n"
        "        return None\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "try:\n"
        "    import agentreplayguard.adapters.httpx\n"
        "except ImportError as exc:\n"
        "    print(str(exc))\n"
        "else:\n"
        "    raise SystemExit('expected ImportError')\n"
    )
    result = _run_python(code)
    assert result.returncode == 0, result.stderr
    assert "agentreplayguard[httpx]" in result.stdout
