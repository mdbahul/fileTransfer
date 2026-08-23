# Learning Log

This file records concepts from the project in a question-and-answer format.

## Milestone 0 — Environment

### Question: What problem does a Python virtual environment solve?

**Your answer:** A virtual environment keeps a project's required dependencies separate, so they do not collide with global packages. It also helps another developer identify and install dependencies.

**Reviewed answer:** Correct in the important sense: a virtual environment gives this project an isolated set of installed Python packages, avoiding conflicts with global packages and other projects.

One distinction: the virtual environment itself is not the shareable list of dependencies. We record that recipe in a file such as `requirements.txt` (or, later, `pyproject.toml`). The virtual environment is the local installed copy; the dependency file tells another developer what to install.

### Question: Why should `.venv/` not be committed to Git?

**Your answer:** Not known yet.

**Reviewed answer:** `.venv/` contains generated files, can make a repository very large, and often contains executables and paths specific to one operating system, CPU architecture, and machine. It is reproducible from the dependency file, so we add `.venv/` to `.gitignore` and commit the dependency file instead.

### Question: What happens if two applications try to listen on the same IP address and TCP port?

**Your answer:** Both applications would get the data.

**Reviewed answer:** Normally, they cannot both listen there. The first server reserves the IP-address-and-port pair (for example, `127.0.0.1:5000`). The operating system rejects the second attempt with an “address already in use” error, because it needs one unambiguous destination for incoming connections.

### Question: A server runs on `127.0.0.1:5000`. What happens if a client tries to connect to `127.0.0.1:5001`, and why?

**Your answer:** The client would not be able to connect.

**Reviewed answer:** Correct. The IP address identifies the same local machine, but `5001` is a different port from `5000`. If no server is listening on `127.0.0.1:5001`, the operating system rejects the connection attempt—typically with a "connection refused" error. A successful TCP connection needs a reachable IP address *and* a listening server at the requested port.

### Question: Which runs first: the TCP client or the server?

**Answer:** Start the server first. It asks the operating system to reserve an address and port, then waits for incoming connections. The client then requests a connection to that address and port. If the client runs before a server is listening, its connection attempt normally fails with "connection refused"; a client can instead be written to retry for a limited time.

### Question: What does `git status --short` show after creating `.gitignore` and `learn.md`?

**Your result:**
```text
?? .gitignore
?? learn.md
```

**Reviewed answer:** `??` means Git sees an untracked file. `.gitignore` is itself a normal project file and should be committed. `learn.md` is also untracked because we deliberately created it as the project's study record. The ignored items do not appear because Git excludes them from normal status output.

### Question: What should `git status --short` show after creating `.venv/`?

**Your result:** Python version: `Python 3.14.0`

```text
?? .gitignore
?? learn.md
```

**Reviewed answer:** Correct. The virtual environment was created, but it does not appear in `git status` because `.venv/` is listed in `.gitignore`. This proves that Git will not accidentally track the machine-specific environment, while the source files and learning log remain visible for review and commit.

### Question: What path should `which python` print after activating `.venv`?

**Your result:**
```text
python: aliased to python3
Python 3.14.0
```

**Reviewed answer:** The version command worked, but the path was not shown because the shell has a `python` alias that expands to `python3`. Aliases are shell text substitutions and can hide the underlying executable from `which`. This does not by itself show whether the virtual environment is active; we must inspect Python's actual executable path and environment prefix.

### Question: How can we verify that the active Python interpreter is inside the virtual environment?

**Your result:**
```text
/Users/new/Desktop/fileTransfer/.venv/bin/python3
/Users/new/Desktop/fileTransfer/.venv
```

**Reviewed answer:** Verified. `sys.executable` identifies the exact Python binary that ran, and it is `.venv/bin/python3`. `sys.prefix` identifies the active Python environment, and it is `.venv`. This is stronger evidence than the Python version alone, because the global interpreter could have the same version.

### Question: What is the practical difference between `git add` and `git commit`?

**Your answer:** `git add` stages changes; commit pushes them.

**Reviewed answer:** Partially correct. `git add` selects the current version of files for the staging area, which is the proposed contents of the next commit. `git commit` records that staged snapshot in the *local* Git repository with a message. It does not send anything to GitHub or another remote; `git push` is the separate command that sends local commits to a configured remote repository.

### Question: What does this `git status --short` output mean?

```text
A  .gitignore
AM learn.md
```

**Reviewed answer:** The first column describes the staging area; the second describes changes in the working directory that have not been staged. `A  .gitignore` means the file is staged as a new file with no later edits. `AM learn.md` means it is staged as a new file, but it was then modified in the working directory. The new learning-log entry must be staged again if it belongs in the same commit.
