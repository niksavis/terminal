from __future__ import annotations

import json
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent


class BuildPyWithHarness(build_py):
    def run(self) -> None:
        super().run()
        target = Path(self.build_lib) / "terminal_setup" / "_harness.json"
        source = ROOT / ".basicly" / "state" / "install.json"
        if source.is_file():
            version = json.loads(source.read_text(encoding="utf-8")).get("basicly_version")
            target.write_text(json.dumps({"basicly_version": version}) + "\n", encoding="utf-8")
            return
        packaged = ROOT / "terminal_setup" / "_harness.json"
        if packaged.is_file():
            shutil.copyfile(packaged, target)


setup(cmdclass={"build_py": BuildPyWithHarness})
