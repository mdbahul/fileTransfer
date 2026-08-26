# Offline File Transfer — Learning Guide

This is a revision guide for the engineering decisions and mental models behind the project. It records durable lessons, not a conversation transcript.

## Current Project State

### Completed

- **Milestone 0:** Python virtual environment, `.gitignore`, and basic Git workflow.
- **Phase 1:** A local TCP client and server exchange a greeting on `127.0.0.1:8080`.
- **Phase 2:** A reusable length-prefixed message protocol frames byte payloads over TCP.
- **Phase 3:** Client streams a file to the server with metadata (filename, size) without loading the entire file into memory.
- **Phase 4:** Client reports cumulative transfer progress and estimated remaining time.
- **Phase 5:** Client and server calculate and verify SHA-256 digests.
- **Phase 7:** Server handles startup, filesystem, connection, metadata, and checksum failures with cleanup.
- **Testing:** Automated integration tests cover binary and zero-byte file transfers.

### Currently Learning

SHA-256 integrity verification for completed transfers.

### Current Architecture

```text
client.py ── TCP connection ──> server.py
    │                              │
    └────── protocol.py ───────────┘
        framing + metadata
```

- `client.py` connects, sends file metadata as a framed message, then streams raw file bytes in chunks.
- `server.py` listens, accepts one client, receives metadata, then writes incoming bytes to a new file until the declared size is reached.
- `protocol.py` owns length-prefix framing, exact reads, and file metadata serialization.
- `progress.py` formats transfer statistics and redraws the five-line terminal progress display.

### Known Limitations

- Localhost only; no LAN discovery or device authentication.
- One client, one file, one direction per server run; no concurrency.
- No timeouts, retry policy, maximum frame size, progress reporting, integrity verification, or resume support.
- No confirmation message from server to client after transfer completes.

### Next Milestone

Add SHA-256 integrity verification for completed transfers.

---

## Milestone 0 — Environment and Git

### Virtual Environments

**What:** A virtual environment is an isolated Python installation for one project.

**Why it matters:** It prevents a project's package versions from colliding with global packages or packages from another project.

**Project use:** `.venv/` contains the local Python environment. It is ignored by Git because it is generated, machine-specific, and reproducible.

**Important distinction:** A virtual environment is the installed local copy of dependencies. A dependency file such as `requirements.txt` or `pyproject.toml` is the shareable installation recipe.

### Git Mental Model

```text
last commit  →  staging area  →  working directory
                 git add          edits
```

- `git add` copies the current file version into the staging area.
- `git commit` creates a local snapshot from the staging area.
- `git push` sends local commits to a configured remote such as GitHub.

`git status --short` has two status columns: the first describes the staging area; the second describes later working-directory changes. For example, `AM learn.md` means the file was staged as new and then modified again locally.

---

## Phase 1 — TCP Sockets

### Network Addressing Mental Model

```text
IP address → which device or network interface?
Port       → which network service on that device?
```

`127.0.0.1` is the IPv4 loopback address. Traffic sent there is routed back to the same computer, making it ideal for early tests because Wi-Fi, routers, firewalls, and a second device are removed from the problem.

`127.0.0.1:8080` identifies a local TCP listener. The server owns the stable destination port; the client uses an OS-selected temporary source port, such as `51322`.

### Socket Lifecycle

```text
Server                              Client
socket()                            socket()
bind(IP, port)
listen()
accept()   <── TCP connection ──    connect(IP, port)
recv()/sendall()  <──────────────>  sendall()/recv()
close()                             close()
```

**Listening socket vs connected socket:** `accept()` returns a new socket for one established client connection. The original listening socket remains available for future connection requests. Data must be sent and received with the connected socket, not the listening socket.

### Blocking I/O

`accept()` blocks while no client is connecting. `recv()` blocks while no data is available, unless a timeout or non-blocking mode is configured. This is why the server appears to pause after printing that it is waiting: it is intentionally waiting inside `accept()`.

### Text and Bytes

TCP transports bytes, so `recv()` returns `bytes`.

```text
Python text (str) --encode("utf-8")--> bytes --TCP--> bytes --decode("utf-8")--> text
```

Only decode data when the protocol says it is text. Arbitrary files are bytes and must not be decoded as UTF-8.

## Decision: TCP for the Initial Transfer Transport

### Problem

The application must deliver ordered file data between two devices.

### Decision

Use TCP sockets for the first implementation.

### Why?

TCP provides a reliable, ordered byte stream and handles retransmission of lost network segments. That gives the application a stable base before we design file-level integrity, resume, and authentication.

### Alternatives

UDP has lower-level datagram semantics and can be useful for discovery or latency-sensitive workloads, but application code must handle ordering, loss, and retransmission itself.

### Tradeoffs

TCP reduces transport-level complexity, but it does not provide application message boundaries, file checksums, authentication, encryption, or resume semantics.

### Debugging Lesson: Address Already in Use

**Symptom:** Binding to `127.0.0.1:5000` failed with an address-in-use error.

**Root cause:** Another process was already listening on port 5000.

**Fix:** Inspect the owner with `lsof -nP -iTCP:5000 -sTCP:LISTEN` and choose a different unused port (`8080`) rather than stopping an unrelated process.

**General lesson:** A TCP listener needs an available IP-address-and-port pair. Check the actual port owner before taking action.

### Resource Cleanup and Fast Restarts

`with socket.socket(...) as socket_name:` closes a socket automatically when the block exits, even if an exception occurs. The server also sets `SO_REUSEADDR` before `bind()` so it can restart promptly after a recently closed local connection. This does not allow two active listeners to share the same endpoint.

---

## Phase 2 — Message Framing

### Corrected Mental Model: TCP Is Not a Message Protocol

**Incorrect assumption:** One `sendall()` on the sender matches one `recv()` on the receiver.

**Correct model:** TCP provides an ordered stream of bytes. It can combine multiple sends into one receive or split one send across multiple receives.

```python
sendall(b"hello")
sendall(b"world")

Possible receiver observations:
recv() → b"helloworld"

or

recv() → b"hell"
recv() → b"oworld"
```

**Why it matters:** The application, not TCP, must define where one message ends and the next begins.

## Decision: Four-Byte Length-Prefixed Frames

### Problem

The client and server need reliable boundaries between metadata, text, and eventually file bytes.

### Decision

Frame every current message as:

```text
[4-byte unsigned payload length][payload bytes]
```

The four-byte length is encoded as `!I`: an unsigned 32-bit integer in network byte order (big-endian).

### Why?

The receiver can first read a fixed-size header, then read exactly the declared number of following bytes. This works for arbitrary binary payloads.

### Alternatives

Delimiter-based framing, such as `[payload]|`, only works if payload bytes can never contain the delimiter or if escaping rules are added. Arbitrary file bytes can contain any delimiter value.

### Tradeoffs

- Supports payloads up to `2^32 - 1` bytes per frame.
- Requires sender and receiver to agree exactly on the header size, format, and byte order.
- The current protocol needs a future maximum frame-size validation rule; an untrusted peer can otherwise claim an impractically large length.

### Consequences

The protocol layer is separate from application behavior. `client.py` and `server.py` decide what a message means; `protocol.py` decides how its bytes are framed.

## Protocol Specification: Version 1

### Purpose

Transfer one arbitrary byte payload as a framed message over an already-connected TCP socket.

#### Frame Layout

```text
┌────────────────┬──────────┬──────────────────────────────────────────┬─────────────────────────────────────┐
│     Field      │   Size   │                 Encoding                 │             Description             │
├────────────────┼──────────┼──────────────────────────────────────────┼─────────────────────────────────────┤
│ Payload length │  4 bytes │ Unsigned integer, !I, network byte order │ Number of payload bytes that follow │
├────────────────┼──────────┼──────────────────────────────────────────┼─────────────────────────────────────┤
│ Payload        │ Variable │ Raw bytes                                │ The message body                    │
└────────────────┴──────────┴──────────────────────────────────────────┴─────────────────────────────────────┘
```

### Sender Procedure

1. Calculate `len(payload)` in bytes.
2. Serialize it with `struct.pack("!I", length)`.
3. Call `sendall()` for the header, then `sendall()` for the payload.

The two `sendall()` calls do not need to remain separate on the network. Correctness comes from byte order and the declared length, not from TCP send boundaries.

### Receiver Procedure

1. Call `recv_exactly(sock, 4)` to obtain a complete header.
2. Decode its length with `struct.unpack("!I", header)`.
3. Call `recv_exactly(sock, length)` to obtain the complete payload.

### Failure Conditions

- If the connection closes before a requested header or payload is complete, `recv_exactly` raises `ConnectionError`.
- If the peers disagree about frame format, the receiver will decode the wrong length and lose stream alignment.
- The current implementation does not yet impose a maximum accepted frame size or timeouts.

### Serialization and Network Byte Order

A Python integer is an in-memory object, not a network representation. `struct.pack` and `struct.unpack` define a shared byte layout. The `!` prefix specifies network byte order so architectures with different native byte orders interpret the length identically.

### Partial Reads and `recv_exactly`

`recv(n)` returns **up to** `n` currently available bytes; it does not promise exactly `n` bytes. `recv_exactly` loops, requesting only the remaining byte count, until it has the requested number of bytes. An empty result (`b""`) before completion means the peer closed the connection.

### Debugging Lesson: Listening Socket vs Connected Socket

**Symptom:** Sending a server reply through `server_socket` raised `OSError: Socket is not connected`.

**Root cause:** `server_socket` is only a listener. The per-client socket returned by `accept()` is `connection`.

**Fix:** Receive and send the client's message through `connection`.

**General lesson:** Keep listener responsibilities separate from per-connection data exchange. This distinction becomes essential when handling multiple clients later.

---

## Phase 3 — Streaming File Transfer

### Why Not Load the Entire File Into Memory?

**Problem:** `open(path, "rb").read()` returns the entire file as one bytes object in RAM. For a 2 GB video file, that is 2 GB of memory
consumed instantly. The process may crash, or the OS may start swapping to disk, making everything slow.

**Solution:** Read the file in small fixed-size pieces (chunks) and send each chunk immediately. At any moment, only one chunk (~4 KB)
lives in memory, regardless of whether the file is 1 MB or 10 GB.

### Mental Model: Streaming

```text
File on disk (any size)
    │
    ├── read 4096 bytes ──→ sendall() ──→ chunk released from memory
    ├── read 4096 bytes ──→ sendall() ──→ chunk released from memory
    │   ...
    └── read last chunk  ──→ sendall() ──→ done
```

Memory usage stays flat. This is the streaming pattern — it applies to any situation where the full data set does not fit comfortably
in memory.

### The Standard Streaming Loop

```python
with open(path, "rb") as f:
    while True:
        chunk = f.read(CHUNK_SIZE)
        if chunk == b"":
            break
        process(chunk)
```

`file.read(n)` returns up to `n` bytes. When the file is exhausted, it returns `b""`. This is the EOF signal. This pattern appears
everywhere: file I/O, network reading, database cursors, any data source of unknown or large size.

### The Receiver's Counting Loop

The receiver knows the total file size from the metadata. It does not need length prefixes on each chunk. Instead, it counts received
bytes:

```python
remaining = file_size
while remaining > 0:
    chunk = connection.recv(min(remaining, CHUNK_SIZE))
    if chunk == b"":
        raise ConnectionError("Connection closed during transfer")
    f.write(chunk)
    remaining -= len(chunk)
```

**Why `min(remaining, CHUNK_SIZE)`?** Without this, the last `recv()` could request more bytes than the file has left, causing the receiver to
block forever waiting for bytes that will never arrive — or to accidentally read bytes belonging to a future protocol message.

**Why subtract `len(chunk)` not `CHUNK_SIZE`?** Because `recv()` can return fewer bytes than requested. The actual number of bytes
received is `len(chunk)`.

### Corrected Mental Model: The Declared File Size Is a Contract

For a zero-byte file, `remaining` starts at zero, so the receive loop does not run. The receiver creates and closes an empty output
file without calling `recv()`.

The declared file size is a protocol contract between sender and receiver. If the sender sends fewer bytes than declared and closes the
connection, the receiver writes only the bytes received and then raises `ConnectionError`. The result is a partial file, not a
successful transfer. If the sender leaves the connection open, the receiver blocks while waiting for the missing bytes.

### Resource Cleanup: `with open(...)`

Always use `with open(path, mode) as f:` instead of `f = open(path, mode)`. The `with` block guarantees the file handle is closed even if an
exception occurs mid-transfer. An unclosed file handle is a resource leak — the OS has a finite number of file descriptors per
process.

### Progress Reporting

Progress is derived from values already available in the streaming loop:

```text
percentage       = transferred_bytes / total_bytes × 100
average_speed    = transferred_bytes / elapsed_seconds
remaining_time   = remaining_bytes / average_speed
```

`time.monotonic()` is used because elapsed-time measurement should not be affected by system clock adjustments. A zero-byte file is
treated as 100% complete, while speed and ETA remain unavailable until there are transferred bytes and positive elapsed time.

The current speed is a cumulative average from the start of the transfer. Printing after every chunk is useful for learning but may be
too noisy for large files; a production UI should throttle updates.

---

### Decision: Whole-File SHA-256 Verification

#### Problem

The receiver currently knows how many bytes arrived, but not whether those bytes are identical to the source file.

#### Decision

The sender calculates SHA-256 incrementally while streaming the file, then sends the resulting 32-byte raw digest in a final framed
checksum message. The receiver calculates SHA-256 incrementally while writing the received bytes, receives the final checksum message,
and compares the two digests.

#### Why?

This avoids reading a large source file twice. The receiver already knows exactly how many raw file bytes to consume from the metadata,
so it can safely read the next framed message after the file stream.

#### Alternatives

A 64-character hexadecimal digest is easier for humans to read and log, but doubles the digest's wire size. Including the digest in
initial metadata would make the metadata self-contained, but requires a separate pre-transfer hash pass. Per-chunk hashes could identify
the location of corruption and support more selective retries, but they add protocol complexity that is not needed yet.

#### Protocol Sequence

```text
1. Framed metadata: filename + file size
2. Raw file bytes: exactly file_size bytes
3. Framed checksum: 32-byte SHA-256 digest
```

#### Module Responsibilities

- `client.py` creates one SHA-256 hash object, updates it for every chunk sent, and sends the final digest.
- `server.py` creates one SHA-256 hash object, updates it for every chunk written, receives the sender's digest, and performs the
  verification.
- `protocol.py` remains responsible only for framing bytes and serializing metadata; hashing is application logic, not transport logic.
- `checksum.py` can hold reusable checksum helpers such as the digest size and a safe digest-comparison function.

#### Failure Policy

A checksum mismatch is an explicit transfer failure. The receiver must not publish the output as a completed file; it should remove or
quarantine the temporary output and report the failure. Automatic retransmission belongs in a later retry layer with bounded attempts,
because repeated failure may indicate a protocol bug, source-file mutation, or disk problem rather than transient network loss.

---

### Decision: Two-Phase Transfer Protocol (Metadata Then Stream)

#### Problem

The receiver needs to know the filename and file size before the raw bytes arrive, but loading the entire file into a single framed
message is not feasible for large files.

#### Decision

Split the transfer into two phases:

```text
Phase 1: Client sends a framed metadata message (filename + file size)
Phase 2: Client streams raw file bytes (no per-chunk framing)
```

#### Why?

The metadata is small and fits naturally in one `send_message()` frame. The file data can be arbitrarily large and must be streamed.
Separating the two means the framing protocol handles structured messages while raw streaming handles bulk data.

#### Alternatives

- Send everything as one giant framed message — fails for large files (memory + `!I` limit).
- Frame every chunk individually — adds overhead and complexity without benefit, since the receiver already knows the total size.

#### Tradeoffs

- Simple and memory-efficient.
- The receiver must trust the declared file size. A malicious or buggy sender could declare a wrong size, causing the receiver to wait
forever or read too few bytes.
- No integrity verification yet — the receiver does not know if the bytes arrived correctly.

### Protocol Specification: File Metadata Message

#### Purpose

Tell the receiver what file is about to be transferred.

#### Layout

```text
┌─────────────────┬──────────┬─────────────────────────────────────────────────┬───────────────────────────────────────────┐
│      Field      │   Size   │                    Encoding                     │                Description                │
├─────────────────┼──────────┼─────────────────────────────────────────────────┼───────────────────────────────────────────┤
│ Filename length │   1 byte │ Unsigned integer, !B                            │ Length of the filename in bytes (max 255) │
├─────────────────┼──────────┼─────────────────────────────────────────────────┼───────────────────────────────────────────┤
│ Filename        │ Variable │ UTF-8 bytes                                     │ The file's name (not a full path)         │
├─────────────────┼──────────┼─────────────────────────────────────────────────┼───────────────────────────────────────────┤
│ File size       │  8 bytes │ Unsigned 64-bit integer, !Q, network byte order │ Total file size in bytes                  │
└─────────────────┴──────────┴─────────────────────────────────────────────────┴───────────────────────────────────────────┘
```

This block is sent as the payload of a standard `send_message()` frame, so the outer `!I` length prefix is handled by the existing framing
layer.

#### Why `!B` for filename length?

Filenames are almost never longer than 255 bytes. A single unsigned byte (`!B`, range 0–255) is sufficient and wastes no space. If the
filename exceeds 255 bytes after UTF-8 encoding, `pack_file_metadata()` raises `ValueError`.

#### Why `!Q` for file size?

A 32-bit unsigned integer (`!I`) maxes out at ~4.29 GB. Files larger than that exist (videos, disk images, datasets). A 64-bit unsigned
integer (`!Q`) supports files up to ~18 exabytes, which is effectively unlimited.

---

## Architecture Evolution

### Version 1 — Direct Socket Calls

`client.py` and `server.py` called `sendall()` and `recv()` directly. This was enough to learn the basic TCP lifecycle but did not establish message boundaries.

### Version 2 — Protocol Module

`protocol.py` now owns `recv_exactly`, `send_message`, and `receive_message`.

**Problem solved:** Client and server can exchange messages reliably even when TCP splits or coalesces bytes.

**New complexity:** Every peer must implement the same frame format, and the application must eventually validate message type and maximum size.

### Version 3 — File Transfer with Metadata

`protocol.py` now also owns `pack_file_metadata` and `unpack_file_metadata`. The client sends a metadata message followed by a raw byte
stream. The server reconstructs the file on disk.

**Problem solved:** Files of any size can be transferred without loading them entirely into memory.

**New complexity:** The receiver trusts the declared file size. No integrity verification, progress reporting, or resume capability exists
yet.

### Version 4 — Progress Renderer

`client.py` now tracks transferred bytes and elapsed time, while `progress.py` renders the percentage, byte counts, speed, and ETA.

Problem solved: Transfer progress is visible without mixing terminal-control logic into the file-transfer loop.

New complexity: ANSI cursor-control sequences vary in support across terminals, and frequent redraws may be noisy or inefficient for
large transfers.

### Version 5 — Checksum Unit Tests

The checksum comparison logic is tested independently with matching, different, and different-length digest values.

Problem solved: Basic integrity-comparison behavior can be verified without starting sockets or transferring files.

Testing lesson: Unit tests isolate one responsibility and make failures easier to diagnose. Integration tests will be needed later to
verify the complete client/server transfer path.

### Version 6 — Testable Transfer Functions

The client and server now expose callable transfer functions, while script execution remains behind `if __name__ == "__main__":`.
Automated integration tests start a server thread, transfer temporary binary files, and verify the received bytes and digest.

Problem solved: The complete transfer path can be tested repeatedly without manually starting two terminal processes or using large
fixture files.

New complexity: The test coordinates server readiness and uses an ephemeral local port, while the transfer functions now return
structured results useful to callers.

---

## Phase 7 — Error Handling

### Decision: Remove Incomplete Files During the Initial Implementation

If a connection closes before the declared file size is received, or checksum verification fails, the receiver deletes the partial
output and reports an unsuccessful transfer. This prevents callers from mistaking an incomplete or corrupted file for a completed one.

### Future Resume-Compatible Policy

When resume support is introduced, the receiver can write to a uniquely identified temporary file and retain it for a bounded period.
Metadata such as transfer ID, expected size, and source digest should be stored with it. A cleanup process can delete abandoned
temporary transfers after a time-to-live expires, while an active retry refreshes that deadline.

The temporary file must never be exposed under the final filename until verification succeeds.

### Error-Handling Tests

Automated integration tests now cover an interrupted transfer, checksum mismatch, unsafe filename, and server startup failure. These
tests verify both the reported failure and the important side effect: incomplete output is not left behind.

### Protocol Tests

The protocol test suite now covers metadata round-tripping, Unicode filenames, filename-length validation, framed message exchange,
successful exact reads, and connection closure before the requested byte count.

Testing lesson: A real `socketpair()` validates end-to-end socket behavior, but it does not guarantee that a single `recv()` returns a
partial result. A deterministic fake socket is needed to specifically test partial-read handling; the test suite now includes one.

### Corrected Testing Mental Model: Sends Do Not Define Receives

Calling `sendall()` twice does not guarantee that the receiver performs two corresponding `recv()` calls. TCP may coalesce the sends
into one read or split them differently. Therefore, the current socket-pair test verifies that the complete byte sequence arrives, but
not specifically that `recv_exactly()` loops across partial reads. A fake socket with predetermined `recv()` results is required for
that exact unit test.

### Integration Result: End-to-End SHA-256 Verification

A large ZIP file was transferred through the real client and server. The source and received files had identical sizes and identical
SHA-256 digests.

This verifies the complete path: streaming reads, TCP transport, bounded receive writes, incremental hashing, final checksum framing,
and receiver-side comparison. It does not yet test failures, retries, temporary-file cleanup, or automated process orchestration.

---

## Interview Revision

1. Why did we choose TCP for the initial transfer transport rather than UDP?
2. Why does `recv(4)` not guarantee a complete four-byte header?
3. How does a length prefix preserve message boundaries over TCP?
4. Why must the server reply through the socket returned by `accept()`?
5. What is the difference between `sendall()` handling partial writes and application-level message framing?
6. What limitations must be addressed before this becomes a secure file-transfer application?
7. Why can't you send a large file as one send_message() call?
8. Why does the streaming loop use min(remaining, CHUNK_SIZE) instead of just CHUNK_SIZE?
9. Why do we subtract len(chunk) instead of CHUNK_SIZE when counting received bytes?
10. Why did we choose `!Q` (64-bit) for the file size instead of `!I` (32-bit)?
11. How does the receiver know when the file transfer is complete without per-chunk framing?