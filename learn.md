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

### Milestone 0 interview review

**Question: Why commit `.gitignore` but not `.venv/`?**

**Your answer:** `.gitignore` tells Git which files to ignore, while `.venv/` is a personal virtual environment containing computer-specific files.

**Review:** Correct. `.gitignore` is shared project configuration; `.venv/` is generated, machine-specific, and reproducible from dependency instructions.

**Question: What does `AM` mean in `git status --short`?**

**Your answer:** Staged as new, then modified again afterward.

**Review:** Correct.

**Question: Does `git commit` publish changes to GitHub?**

**Your answer:** No. It saves a local snapshot; `git push` sends it to GitHub.

**Review:** Correct.

### Git short-status reference

`git status --short` normally uses two columns: `XY path`. `X` is the staged status (the index); `Y` is the unstaged working-directory status. A space means no change in that column.

| Code | Meaning |
| --- | --- |
| `M` | Modified |
| `A` | Added as a new tracked file |
| `D` | Deleted |
| `R` | Renamed |
| `C` | Copied |
| `U` | Unmerged; Git needs help resolving a merge conflict |
| `??` | Untracked; Git has never been told to track the file |
| `!!` | Ignored by a `.gitignore` rule (shown only with `--ignored`) |

Examples: ` M file.py` is modified but not staged; `M  file.py` is a modification staged for the next commit; `MM file.py` has one modification staged and another unstaged; `D  file.py` has a deletion staged; ` D file.py` was deleted locally but the deletion is not staged; and `AM file.py` was added to the staged snapshot, then edited again locally.

## Phase 1 — TCP Sockets

### Question: What is a network in the context of this application?

**Answer:** A network is a collection of devices that can exchange data according to shared rules. For this project, the first network will be one computer talking to itself; later, it will be a local area network (LAN) connecting nearby devices without a cloud server.

### Question: What is an IP address?

**Answer:** An IP address identifies a network interface so that data can be routed to the right machine or device. `127.0.0.1` is the IPv4 loopback address: it routes data back to the same computer and is useful for safe local testing.

### Question: What is a port?

**Answer:** A port is a 16-bit number that identifies the destination application or service on a device. An IP address gets data to a device; the port gets it to the intended program. A TCP listener normally reserves an IP-address-and-port pair, such as `127.0.0.1:5000`.

### Question: What is a socket?

**Answer:** A socket is an operating-system-managed endpoint a program uses to communicate over a network. A TCP server has a listening socket; after accepting a client, it gets a separate connected socket for exchanging bytes with that client.

### Question: What is TCP?

**Answer:** Transmission Control Protocol (TCP) is a transport protocol that provides an ordered, reliable byte stream between two connected endpoints. It retransmits lost data and detects many connection failures, but it does not create application-level message boundaries or guarantee that an application successfully processes received data.

### Question: What is the client/server lifecycle?

**Answer:** The server creates a socket, binds it to an address and port, starts listening, and accepts a connection. The client creates a socket and connects to that address and port. The connected sockets exchange bytes, then both sides close them. The client must connect only after the server is listening, unless it has retry logic.

### Exercise: Why do developers use `127.0.0.1` before a Wi-Fi IP address, and what role do the IP address and port each play in `127.0.0.1:5000`?

**Your answer:** `127.0.0.1` is the loopback address, so it lets us test code locally. The IP address identifies the device and the port identifies the process.

**Reviewed answer:** The loopback explanation is correct: local testing removes Wi-Fi, router, firewall, and second-device variables while we learn socket behavior. The IP-address explanation is also correct. More precisely, a port identifies a network service or socket endpoint on the device, not necessarily one operating-system process. One process can listen on multiple ports, and a process can manage many connected sockets.

### Question: Why does the server use `accept()` to obtain a separate connected socket instead of using its listening socket to exchange data with every client?

**Your answer:** Because the server can connect to multiple clients.

**Reviewed answer:** Correct. The listening socket has one job: receive new connection requests. Each call to `accept()` produces a separate connected socket for one client, while the original listening socket remains available to accept others. This separation lets the server keep accepting clients and keeps each client's byte stream independent. A connected TCP socket is identified by the local and remote address-and-port pairs.

### Exercise: Describe the basic server lifecycle in pseudocode.

**Your answer:** Initialize a socket, bind an IP address and port, listen, accept, send and receive until the work is done, then close.

**Reviewed answer:** Correct. The listening socket is created, bound, and placed in listening mode. `accept()` returns a new connected socket that performs `send` and `recv` for one client. At the end, close the connected socket and, when the server is finished accepting clients, close the listening socket too. Closing releases OS resources and makes the port available again.

### Question: What type does `recv()` return, and why?

**Your answer:** `bytes`.

**Reviewed answer:** Correct. TCP transports raw bytes, not Python text strings. `recv()` therefore returns `bytes`, which can represent any file content—including images and other binary data. When our protocol sends text, we will explicitly convert between text and bytes with an encoding such as UTF-8 using `.encode()` and `.decode()`.

### First server implementation review

**What was correct:** The first attempt follows the core server sequence: create a socket, bind it, listen, accept a connection, and close the accepted client socket. `accept()` correctly returns the connected socket and the client's address.

**Required improvements:** Use `socket.AF_INET` and `socket.SOCK_STREAM` explicitly so the code communicates the IPv4/TCP design. Bind specifically to `127.0.0.1` and port `5000` for safe local testing; an empty host string generally binds to all local network interfaces. Print a waiting message before `accept()` and print the client address after it returns. Use `recv(1024)` to read the client's bytes and `sendall(b"Hello from server")` to reply. Finally, close the listening socket as well as the connected client socket.

### Revised server implementation review

**What improved:** The server now explicitly selects IPv4 (`AF_INET`) and TCP (`SOCK_STREAM`), binds only to `127.0.0.1:5000`, prints before its blocking `accept()` call, receives up to 1024 bytes, sends a byte-string reply with `sendall`, and closes both sockets.

**One remaining change:** Print `addr` immediately after `accept()` so we can see the client IP address and its temporary source port. If the backslashes shown in the pasted code are actually present in `server.py`, remove them; they are unnecessary and would make the source invalid. If they are only chat formatting, no change is needed.

### Debugging case: `Address already in use`

**Observed result:** Binding to port `5000` failed because it was already in use. Changing to port `8080` allowed the server to print its waiting message.

**What the error means:** The failure occurs during `bind()`, before `listen()` or `accept()`. Another socket has already reserved the requested IP-address-and-port pair, so the operating system cannot give the same listening endpoint to this server. The waiting message on port `8080` is evidence that binding and listening succeeded and that `accept()` is now blocking for a client.

**Next diagnostic:** On macOS, `lsof -nP -iTCP:5000 -sTCP:LISTEN` asks which process, if any, is listening on TCP port 5000. This is a read-only diagnostic; inspect its output before deciding whether to stop a process or keep using another port.

### Debugging result: identify the port owner

**Your result:** `lsof` showed process `ControlCe` with PID `674` listening on TCP port `5000` for IPv4 and IPv6.

**Reviewed answer:** This confirms that another process owns port 5000. `*:5000 (LISTEN)` means it listens on all available network interfaces, not only loopback. Because it is unrelated to this project, we should not stop it; choosing another available port such as 8080 is the safe and correct solution. The process identifier (PID) is useful when a process *is* ours and we need to investigate or stop it deliberately.

### Question: What will happen when a client calls `connect(("127.0.0.1", 8080))` while the server is blocked in `accept()`?

**Your answer:** Implemented a client that successfully connected to `127.0.0.1:8080`, sent `"Hello from client"`, and received the server reply.

**Reviewed answer:** Correct in behavior. The client's `connect()` initiated the TCP connection setup. Once the OS established the connection, the server's blocked `accept()` call returned a new connected socket and the client's address. The client then sent encoded text bytes; the server received those bytes and replied; the client received the reply as bytes.

### First client implementation review

**What was correct:** The client explicitly selects IPv4/TCP, connects to the same local address and port as the server, encodes the text message before `sendall`, receives the byte-string reply, and closes the socket.

**Improvements to make next:** Use the `port` variable in `connect(("127.0.0.1", port))` instead of repeating the number `8080`; otherwise changing the variable later would not change the actual connection target. Print a clear message before connecting and decode the received reply for human-friendly text output. Keep `sendall` rather than `send` because it handles partial writes of the supplied byte string for us.

### End-to-end handshake verification

**Observed server output:**
```text
waiting for client
('127.0.0.1', 49941)
Hello from client
```

**Observed client output:**
```text
Hello from server
```

**Reviewed result:** Verified. The server listened at its fixed endpoint `127.0.0.1:8080`. The accepted address shows that the client connected from loopback address `127.0.0.1` using temporary source port `49941`, selected by the operating system. The client-to-server and server-to-client messages were both exchanged successfully. The plain-text output also confirms that the code decoded received UTF-8 text before printing it.

### Phase 1 interview review

**Question: Why must the server start listening before the client connects?**

**Your answer:** The server should start before the client so it can accept requests from the client.

**Review:** Correct. Before listening, no OS socket is available at the requested IP-address-and-port endpoint, so a client connection attempt is normally refused.

**Question: What are the two values inside `('127.0.0.1', 49941)`?**

**Your answer:** One is the address; the other is the port.

**Review:** Correct. They are the client's IP address and temporary source port.

**Question: Why use `.encode()` before `sendall()` and `.decode()` after `recv()`?**

**Your answer:** `.encode()` gets data into the correct text format rather than binary format.

**Review:** Partially correct, but the direction is reversed. `.encode()` converts Python text (`str`) into bytes, because TCP sends bytes. `.decode()` converts received bytes back into Python text for display or text processing. Binary files should remain bytes and must not be decoded as text.

### Cleanup: automatic socket closure and address reuse

**Question: Why use `with socket.socket(...) as socket_name`?**

**Answer:** A context manager guarantees that the socket's `close()` method runs when execution leaves the `with` block, including when an exception occurs. It prevents the manual cleanup code from being forgotten or skipped on an early failure.

**Question: Why set `SO_REUSEADDR` before `bind()` on this development server?**

**Answer:** After a TCP connection closes, the operating system can temporarily retain connection state even though no listener appears in `lsof`. Setting `SO_REUSEADDR` before binding lets this local development server restart promptly on the same address and port. It does not allow two active listeners to own the same endpoint at once, and it must be set before `bind()`.

**Verification:** The cleaned server accepted a client from temporary port `50091`, received `Hello from client`, sent its reply, and exited with status 0. The client printed `Server replied: Hello from server` and exited with status 0.
