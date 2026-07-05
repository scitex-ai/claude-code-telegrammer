---
description: |
  [TOPIC] Interface Python Api Docstrings
  [DETAILS] NumPy-style docstrings for every public function — Parameters, Returns, Examples sections. Module docstrings carry purpose + Functionalities/IO/Dependencies blocks. One-liners are insufficient for `__all__` members. Sphinx autodoc + LLM readability both benefit.
tags: [scitex-general-interface-python-api-docstring-standards]
---

# Docstring Standards

## NumPy style for every public function

```python
def save(obj, path, *, dry_run=False, overwrite=False):
    """Save a Python object to disk based on path extension.

    Dispatches on object type and file extension. CSV for DataFrames, NPY for
    arrays, PKL for arbitrary objects. See `list_formats()` for the registry.

    Parameters
    ----------
    obj : Any
        Object to serialize. Supported types: pandas.DataFrame, numpy.ndarray,
        matplotlib.figure.Figure, dict, list, or any pickleable object.
    path : str or pathlib.Path
        Destination path. Extension determines the writer.
    dry_run : bool, default False
        If True, validate the operation without writing to disk. Returns the
        path that would be written.
    overwrite : bool, default False
        If False and `path` exists, raises FileExistsError.

    Returns
    -------
    pathlib.Path
        The resolved absolute path that was written (or would be written, if
        `dry_run=True`).

    Raises
    ------
    FileExistsError
        If `overwrite=False` and `path` already exists.
    ValueError
        If the file extension has no registered saver.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({"a": [1, 2, 3]})
    >>> save(df, "results.csv")
    PosixPath('/abs/path/results.csv')

    >>> save(df, "results.csv", dry_run=True)   # No write
    PosixPath('/abs/path/results.csv')
    """
```

## Required sections (in order)

| Section          | Required for `__all__` member? | Notes                                              |
|------------------|-------------------------------|----------------------------------------------------|
| Summary line     | ✅ always                      | One sentence, imperative voice ("Save", "Load")     |
| Body paragraph   | recommended                   | Why this exists, what it dispatches on              |
| Parameters       | ✅ if function takes args      | Every param documented, with type + default         |
| Returns          | ✅ if function returns         | Type + meaning                                      |
| Raises           | recommended                   | Each exception class + when                         |
| Examples         | ✅ for high-traffic functions  | Doctest-runnable; show the common case              |
| See Also         | optional                      | Sibling functions                                   |
| Notes            | optional                      | Deferred constraints, performance hints             |

## Module docstrings

```python
# scitex_io/_save.py
"""Polymorphic save() — dispatches on object type and file extension.

Functionalities
---------------
- save() top-level entry point
- _save_csv, _save_npy, _save_pkl as private dispatch targets
- Registry lookup via _registry.SAVERS

IO
--
- Inputs: any registered Python object + path
- Outputs: file on disk, returns absolute Path
- Side effects: creates parent directories if missing

Dependencies
------------
- pandas (optional, for DataFrame support)
- numpy  (optional, for ndarray support)
- joblib (optional, for parallel pickle)
"""
```

The `Functionalities / IO / Dependencies` triple helps LLM agents quickly understand a private module without reading the body. Apply to every implementation file.

## Top-level `__init__.py` docstring

```python
# scitex_io/__init__.py
"""scitex_io — Universal file I/O for scientific Python.

30+ formats with extension-based dispatch. CSV, NPY, PKL, HDF5, Zarr, ...

Quick Start
-----------
>>> import scitex_io as sio
>>> sio.save(df, "results.csv")
>>> df = sio.load("results.csv")

Submodules
----------
formats : list_formats() and per-format helpers
metadata: embed_metadata, read_metadata
"""
```

Show the smallest possible "hello world" — users skim package docstrings; reward that with the import + one save + one load.

## Why this rigor

- **Sphinx autodoc** reads NumPy style natively; less rigorous styles render poorly.
- **LLM agents** parse Parameters/Returns reliably to construct calls; bullet prose forces guessing.
- **`help(scitex_io.save)`** in a REPL is the user's first encounter — make it carry weight.
- **`scitex-dev introspect api scitex_io -vvv`** dumps full docstrings; CI can lint them.

## Audit

```bash
scitex-dev introspect api scitex_io -vvv | less
```

Failure modes:

- One-line docstring on a multi-arg public function → insufficient.
- Missing `Parameters` block when args exist → fails NumPy parser.
- `Examples` block missing on top-traffic functions (`save`, `load`, `run_test`) → SciTeX-specific gate.
- Docstring describes WHAT the code does without WHY anyone calls it → rewrite.

Linter rule (planned): **PA-008** — every `__all__` member must have a NumPy-conformant docstring with Parameters + Returns.
