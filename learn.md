# Offline File Transfer — Learning Guide

This is a revision guide for the engineering decisions and mental models behind the project. It records durable lessons, not a conversation transcript.

## Current Project State

### Completed

- **Milestone 0:** Python virtual environment, `.gitignore`, and basic Git workflow.
- **Phase 1:** A local TCP client and server exchange a greeting on `127.0.0.1:8080`.
- **Phase 2:** A reusable length-prefixed message protocol frames byte payloads over TCP.

### Currently Learning

How to transfer files as a stream of bytes without loading the entire file into memory.

### Current Architecture

```text
client.py ── TCP connection ──> server.py
    │                              │
    └────── protocol.py ───────────┘
             framing only
```

- `client.py` connects, sends one framed text message, and receives one framed reply.
- `server.py` listens, accepts one client, receives one framed text message, and replies.
- `protocol.py` owns length-prefix serialization and exact reads.

### Known Limitations

- Localhost only; no LAN discovery or device authentication.
- One client and one message per server run; no concurrency.
- No timeouts, retry policy, message types, maximum frame size, or file transfer yet.
- Payloads are treated as UTF-8 text by the demo programs; files must remain raw bytes in the next phase.

### Next Milestone

Stream a file with metadata (name and size) without loading the whole file into RAM.

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

```text
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

### Frame Layout

| Field | Size | Encoding | Description |
| --- | ---: | --- | --- |
| Payload length | 4 bytes | Unsigned integer, `!I`, network byte order | Number of payload bytes that follow |
| Payload | Variable | Raw bytes | The message body |

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

## Architecture Evolution

### Version 1 — Direct Socket Calls

`client.py` and `server.py` called `sendall()` and `recv()` directly. This was enough to learn the basic TCP lifecycle but did not establish message boundaries.

### Version 2 — Protocol Module

`protocol.py` now owns `recv_exactly`, `send_message`, and `receive_message`.

**Problem solved:** Client and server can exchange messages reliably even when TCP splits or coalesces bytes.

**New complexity:** Every peer must implement the same frame format, and the application must eventually validate message type and maximum size.

---

## Interview Revision

1. Why did we choose TCP for the initial transfer transport rather than UDP?
2. Why does `recv(4)` not guarantee a complete four-byte header?
3. How does a length prefix preserve message boundaries over TCP?
4. Why must the server reply through the socket returned by `accept()`?
5. What is the difference between `sendall()` handling partial writes and application-level message framing?
6. What limitations must be addressed before this becomes a secure file-transfer application?
