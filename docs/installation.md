---
description: >-
  Install StepUp Queue with pip on Linux, macOS or WSL,
  on Python 3.11 or later, which also installs StepUp Core.
---

<!--
SPDX-FileCopyrightText: 2025 Toon Verstraelen <Toon.Verstraelen@UGent.be>
SPDX-License-Identifier: CC-BY-SA-4.0
-->

# Installation

Requirements:

- [POSIX](https://en.wikipedia.org/wiki/POSIX) operating system: Linux, macOS or WSL.
  StepUp cannot run natively on Windows.
- [Python](https://www.python.org/) ≥ 3.11
- [Pip](https://pip.pypa.io/)

It is assumed that you know how to use [Pip](https://pip.pypa.io/).
We recommend performing the installation in a
[Python virtual environment](https://docs.python.org/3/library/venv.html)
and activating such environments with [direnv](https://direnv.net/).

StepUp Queue can be installed with:

```bash
pip install stepup-queue
```

(This will also install [StepUp Core](https://reproducible-reporting.github.io/stepup-core/).)
