# Installation

```bash
pip install tl_elliptec
```

Requires Python 3.9+ and [pyserial](https://pyserial.readthedocs.io/), which
is installed automatically as a dependency.

## From source

```bash
git clone https://github.com/TapyrLabs/tl_elliptec
cd tl_elliptec
pip install -e ".[test]"
```

## Running the tests

```bash
pytest
```

No hardware is required — the test suite runs against a scripted fake bus
and checks values against the manual's own worked examples (e.g. section
4's `Ama00002000` → `APO00002000`, and the `0I1100428FFFFFFFF00BD008B`
motor-info example).
