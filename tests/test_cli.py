"""Tests for the unified weilink CLI."""

import json
import subprocess
import sys


class TestCLIArgParsing:
    """Tests for CLI argument parsing without starting servers."""

    def test_no_subcommand_shows_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_admin_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli", "admin", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--host" in result.stdout
        assert "--port" in result.stdout
        assert "--base-path" in result.stdout

    def test_mcp_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "weilink.cli", "mcp", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--transport" in result.stdout
        assert "stdio" in result.stdout
        assert "sse" in result.stdout
        assert "streamable-http" in result.stdout
        assert "http" in result.stdout
        assert "--admin-port" in result.stdout


class TestCLIAdmin:
    """Tests for the admin subcommand via the unified CLI."""

    def test_admin_starts_and_responds(self, tmp_path):
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "weilink.cli",
                "admin",
                "--port",
                "0",
                "-d",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.stdout is not None
            url = None
            for _ in range(50):
                line = proc.stdout.readline()
                if "running at" in line:
                    url = line.strip().split()[-1]
                    break
            assert url is not None, "CLI did not print the URL"

            import urllib.request

            req = urllib.request.Request(url + "/api/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            assert "version" in data
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_admin_via_legacy_entry_point(self, tmp_path):
        """weilink-admin (via python -m weilink.admin) delegates to unified CLI."""
        proc = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "weilink.admin",
                "--port",
                "0",
                "-d",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.stdout is not None
            url = None
            for _ in range(50):
                line = proc.stdout.readline()
                if "running at" in line:
                    url = line.strip().split()[-1]
                    break
            assert url is not None, "Legacy CLI did not print the URL"
        finally:
            proc.terminate()
            proc.wait(timeout=5)
