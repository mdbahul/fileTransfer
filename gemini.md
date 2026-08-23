# Offline File Transfer Application

## Project Overview

Build a production-quality **offline file-transfer application** that allows users to transfer files directly between nearby devices without requiring the internet.

The primary goal is to use this project to deeply understand and demonstrate:

* Computer networking
* TCP/IP
* Socket programming
* Client-server architecture
* Network discovery
* Concurrent connections
* File I/O
* Chunked data transfer
* Checksums and data integrity
* Authentication
* Error handling
* Interrupted-transfer recovery
* Cross-platform development
* Testing
* Git and software engineering practices
* Basic system design

This is an educational project, but the implementation should follow professional software-engineering practices.

---

# Target Platforms

The long-term goal is to support:

* macOS
* Windows
* Android

The initial implementation can focus on **macOS/Windows using Python**, with Android support added later.

The application should work over a local network without requiring internet access.

Possible future transports:

* Wi-Fi LAN
* Mobile hotspot
* Wi-Fi Direct where platform support permits

Do NOT depend on a cloud server for file transfer.

---

# High-Level Architecture

The target architecture is:

```text
             Local Network
                  │
        ┌─────────┴─────────┐
        │                   │
   Device A             Device B
        │                   │
        └──── Discovery ────┘
                  │
           Authentication
                  │
            TCP Connection
                  │
           File Transfer
                  │
             Chunking
                  │
          Checksum / Hash
                  │
          Verification
                  │
        Resume if interrupted
```

A device should be able to act as either:

* Sender
* Receiver

Ideally, every device should be capable of both roles.

---

# Core Features

## Phase 1 — Basic Communication

Implement a basic TCP client/server system.

Requirements:

* Start a server on a configurable port.
* Allow a client to connect.
* Exchange messages.
* Handle connection termination cleanly.
* Handle connection errors.
* Use Python's standard `socket` library.

The first milestone is:

```text
Client → Server
"Hello"
Server → Client
"Hello from server"
```

Do not introduce unnecessary frameworks at this stage.

The purpose is to understand sockets properly.

---

# Phase 2 — File Transfer

Implement file transfer over TCP.

Requirements:

* Select a file.
* Send metadata before file contents.
* Transfer the file in chunks.
* Write received chunks to disk.
* Handle files larger than available RAM.

Never load an entire file into memory.

Use streaming/chunked I/O:

```python
with open(file_path, "rb") as file:
    while chunk := file.read(CHUNK_SIZE):
        send(chunk)
```

The receiver should similarly write chunks directly to disk.

---

# File Transfer Protocol

Design an explicit application-level protocol instead of blindly sending raw bytes.

Example:

```text
[HEADER]
    protocol version
    message type
    filename
    file size
    checksum
    transfer ID

[DATA]
    chunk
    chunk
    chunk
    ...

[END]
    transfer complete
```

The protocol should be documented before it becomes complicated.

Prefer structured metadata such as JSON followed by binary data.

Do not mix arbitrary JSON and binary data without clearly defining message boundaries.

---

# Phase 3 — File Integrity

Every transfer should eventually support integrity verification.

Calculate a cryptographic hash such as SHA-256.

Example:

```text
Sender
   ↓
Calculate SHA-256
   ↓
Send metadata
   ↓
Transfer file
   ↓
Receiver calculates SHA-256
   ↓
Compare hashes
   ↓
PASS / FAIL
```

If the hashes differ:

```text
TRANSFER FAILED
REASON: checksum mismatch
```

Do not silently accept corrupted files.

---

# Phase 4 — Device Discovery

Users should not have to manually enter IP addresses.

Implement local-network discovery.

Possible approaches:

* UDP broadcast
* UDP multicast
* mDNS/Bonjour
* Zeroconf

Start with the simplest approach that allows the concepts to be understood clearly.

Example:

```text
Device A
   │
   │ UDP broadcast
   ↓
"FILE_TRANSFER_DISCOVERY"
   │
   ↓
Device B
   │
   └──→ "Device B, port 5000"
```

Discovery and file transfer should remain separate components.

Discovery finds devices.

TCP handles the actual transfer.

---

# Phase 5 — Authentication

Before accepting a file transfer, establish that the connecting device is authorized.

Possible design:

```text
Device A
   │
   │ Connection
   ↓
Device B
   │
   │ Authentication challenge
   ↓
Device A
   │
   │ Response
   ↓
Authenticated
```

Possible mechanisms:

* One-time PIN
* Pairing code
* Pre-shared token
* Public-key authentication

Start with a simple pairing mechanism and improve it later.

Never implement authentication by sending passwords in plaintext.

---

# Phase 6 — Concurrent Transfers

The server should support multiple connections.

Example:

```text
                    ┌── Device A
                    │
Server ─────────────┼── Device B
                    │
                    └── Device C
```

Possible implementations:

### Option 1

Thread per connection.

### Option 2

`asyncio`.

### Option 3

Thread pool.

Start with the simplest understandable implementation.

Do not optimize prematurely.

The code should make concurrency concepts obvious.

---

# Phase 7 — Resume Interrupted Transfers

The application should eventually support interrupted transfers.

Example:

```text
1 GB file
    ↓
Transferred: 640 MB
    ↓
Connection lost
    ↓
Reconnect
    ↓
Resume from 640 MB
    ↓
Complete
```

The protocol should track:

```text
transfer_id
file_size
chunk_size
current_offset
checksum
```

The receiver should be able to tell the sender:

```text
RESUME_FROM = 671088640
```

The sender then continues from that offset.

Avoid retransmitting the entire file unnecessarily.

---

# Phase 8 — Progress Reporting

Show transfer progress:

```text
Sending: movie.mp4

████████████████░░░░  78%

Transferred: 780 MB / 1 GB
Speed: 42.3 MB/s
ETA: 6 seconds
```

Track:

* Bytes transferred
* Total bytes
* Percentage
* Transfer speed
* Estimated time remaining

Keep the transfer engine independent from the UI.

---

# Suggested Project Structure

The exact structure can evolve, but aim toward something like:

```text
fileTransfer/
│
├── README.md
├── gemini.md
├── requirements.txt
├── .gitignore
│
├── src/
│   ├── server.py
│   ├── client.py
│   │
│   ├── networking/
│   │   ├── tcp.py
│   │   ├── discovery.py
│   │   └── protocol.py
│   │
│   ├── transfer/
│   │   ├── sender.py
│   │   ├── receiver.py
│   │   ├── chunking.py
│   │   ├── checksum.py
│   │   └── resume.py
│   │
│   ├── security/
│   │   └── authentication.py
│   │
│   └── utils/
│       ├── logging.py
│       └── helpers.py
│
├── tests/
│   ├── test_protocol.py
│   ├── test_transfer.py
│   ├── test_checksum.py
│   └── test_resume.py
│
└── docs/
    ├── architecture.md
    └── protocol.md
```

Do not create all of these files immediately.

Create structure incrementally as functionality requires it.

---

# Engineering Principles

## 1. Understand Before Abstracting

Do not introduce abstractions merely to make the project look sophisticated.

Prefer:

```text
simple working implementation
        ↓
understand it
        ↓
identify repeated logic
        ↓
refactor
```

over:

```text
huge architecture
        ↓
unclear behavior
```

---

## 2. Keep Components Separated

The following responsibilities should remain separate:

```text
Discovery
   ↓
Connection
   ↓
Protocol
   ↓
Transfer
   ↓
Integrity
   ↓
Resume
   ↓
UI
```

For example:

`discovery.py` should not contain file-transfer logic.

`checksum.py` should not know how TCP connections work.

---

## 3. Fail Explicitly

Never silently ignore errors.

Handle cases such as:

* Connection refused
* Connection reset
* Timeout
* File not found
* Permission denied
* Disk full
* Corrupted transfer
* Invalid protocol message
* Unsupported protocol version
* Authentication failure
* Interrupted transfer

Errors should be meaningful and actionable.

---

# Networking Requirements

Understand and document:

* IP addresses
* Ports
* TCP
* UDP
* Sockets
* `bind()`
* `listen()`
* `accept()`
* `connect()`
* `send()`
* `sendall()`
* `recv()`
* Connection lifecycle
* TCP stream semantics
* Partial reads/writes
* Timeouts
* Connection termination

Important:

TCP is a **byte stream**, not a message protocol.

Therefore, never assume:

```python
recv(1024)
```

returns exactly one application-level message.

The application protocol must define message boundaries.

---

# File Transfer Requirements

Use streaming I/O.

Never do:

```python
data = file.read()
socket.send(data)
```

for potentially large files.

Instead:

```text
File
 ↓
Chunk
 ↓
TCP
 ↓
Chunk
 ↓
Disk
```

The chunk size should be configurable.

Start with a reasonable value such as:

```text
64 KB
```

and benchmark before changing it.

---

# Security Principles

Even though the application operates offline, do not assume the local network is trusted.

Potential threats include:

* Unauthorized devices
* Malicious file names
* Path traversal
* Man-in-the-middle attacks
* Malicious payloads
* Denial of service
* Arbitrarily large file metadata
* Resource exhaustion

Never allow a received filename such as:

```text
../../important_file
```

to escape the intended download directory.

Sanitize filenames and control the destination path.

Do not execute received files.

---

# Testing Strategy

Test at multiple levels.

## Unit Tests

Test:

* Protocol encoding/decoding
* Checksum calculation
* Filename sanitization
* Chunk generation
* Resume offset calculation

## Integration Tests

Test:

```text
Client ↔ Server
```

with:

* Small files
* Large files
* Empty files
* Binary files
* Unicode filenames
* Interrupted transfers
* Corrupted transfers

## Network Failure Tests

Simulate:

* Connection drop
* Timeout
* Server shutdown
* Client shutdown
* Partial transfer
* Invalid packets/messages

A transfer is not considered reliable until failure cases are tested.

---

# Git Practices

Use Git throughout development.

Commit logical milestones.

Examples:

```text
feat: implement basic TCP server
feat: implement TCP client
feat: add message protocol
feat: implement file transfer
feat: add SHA-256 verification
feat: add device discovery
feat: add authentication
feat: add transfer resume
test: add interrupted transfer tests
refactor: separate protocol from transport
```

Avoid huge commits containing unrelated changes.

---

# Development Strategy

Build vertically instead of implementing every subsystem independently.

Recommended progression:

```text
1. TCP client/server
        ↓
2. Message exchange
        ↓
3. File transfer
        ↓
4. File metadata
        ↓
5. SHA-256 verification
        ↓
6. Better protocol
        ↓
7. Device discovery
        ↓
8. Authentication
        ↓
9. Concurrent transfers
        ↓
10. Progress reporting
        ↓
11. Resume interrupted transfers
        ↓
12. Cross-platform testing
        ↓
13. Android client
```

At every stage:

```text
Implement
   ↓
Test
   ↓
Understand
   ↓
Commit
   ↓
Document
   ↓
Move forward
```

---

# Gemini CLI Instructions

When helping with this project:

1. **Do not rewrite the entire project unnecessarily.**
2. Inspect the existing code before suggesting changes.
3. Preserve working functionality.
4. Make the smallest reasonable change.
5. Explain important networking concepts when they appear.
6. Prefer standard Python libraries initially.
7. Do not add dependencies without a clear reason.
8. Do not introduce frameworks prematurely.
9. Write testable code.
10. Consider macOS, Windows, and eventually Android compatibility.
11. When changing the protocol, update the protocol documentation.
12. When adding a feature, add or update tests.
13. Never hide exceptions just to make the application appear to work.
14. Never hard-code machine-specific IP addresses or paths.
15. Never expose secrets or authentication tokens in source code.
16. Keep backward compatibility in mind when changing the protocol.

---

# Interview-Oriented Goals

This project should eventually allow the developer to confidently explain:

### Networking

* How TCP works
* TCP vs UDP
* Three-way handshake
* TCP streams
* Sockets
* Ports
* IP addressing
* Local-network communication
* UDP discovery
* Connection failures

### System Design

* Client-server architecture
* Peer-to-peer architecture
* Service discovery
* Protocol design
* Chunking
* Backpressure
* Concurrency
* Reliability
* Fault tolerance
* Data integrity
* Resumable transfers

### Software Engineering

* Modular architecture
* Testing
* Logging
* Error handling
* Git
* API/protocol versioning
* Cross-platform development

The project should not merely "work".

The developer should understand **why every major design decision was made**.

---

# Current Priority

Do not jump directly to Android, GUI, authentication, or advanced discovery.

First build a solid foundation:

```text
TCP
 ↓
Client/server
 ↓
Message protocol
 ↓
File transfer
 ↓
Checksum
```

Only after these are reliable should advanced functionality be added.

The project should grow incrementally rather than becoming a large unfinished codebase.
