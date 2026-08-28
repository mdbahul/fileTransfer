# Offline File Transfer - Technical Documentation

This document describes the current implementation of the offline file
transfer application. It focuses on architecture, networking behavior,
protocol details, reliability, testing, and known limitations.

## 1. Current Architecture

The application uses a peer-to-peer workflow with separate discovery and
transfer channels:

```text
Client
  |
  | UDP broadcast discovery
  v
Receiver IP address and TCP port
  |
  | TCP connection
  v
Receiver approval
  |
  | Framed metadata and streamed bytes
  v
Checksum verification and atomic publication
```

### Components

| Module | Responsibility |
| --- | --- |
| `client.py` | Selects a file, discovers devices, sends metadata and file data |
| `server.py` | Listens for TCP clients, approves transfers, receives files |
| `discovery.py` | Sends and receives UDP discovery messages |
| `protocol.py` | Defines binary framing and transfer control messages |
| `utils.py` | Filename validation, byte formatting, cleanup, filesystem sync |
| `progress.py` | Renders terminal progress and transfer statistics |
| `checksum.py` | Compares digests using constant-time comparison |

The normal server uses `serve()`, which keeps one TCP listener open and starts
one worker thread per accepted connection. `receive_file()` remains a
one-transfer helper for programmatic use and tests.

## 2. Network Behavior

### TCP server

The server binds to `0.0.0.0` by default so devices on the local network can
connect. Its default TCP port is `0`, which asks the operating system to
select an available port.

The server must bind before starting discovery:

```text
bind TCP port 0
  -> read actual port with getsockname()
  -> start UDP discovery listener
  -> advertise the actual TCP port
```

This avoids port conflicts and ensures that discovery advertises the port
that is actually listening.

### UDP discovery

The client broadcasts this request on UDP port `37020`:

```text
FILE_TRANSFER_DISCOVERY|1
```

The receiver responds with a UTF-8 JSON message containing:

```json
{
  "type": "FILE_TRANSFER_DEVICE",
  "version": 1,
  "device_name": "Laptop",
  "tcp_port": 49152
}
```

The sender obtains the receiver IP address from the UDP packet's source
address. The response payload supplies the TCP port.

UDP is used only for discovery. It is connectionless and unreliable, so
responses may be lost. TCP handles all file data.

## 3. TCP Protocol

TCP provides an ordered byte stream, not message boundaries. Every control
message therefore uses this frame:

```text
[4-byte unsigned payload length, network byte order]
[payload bytes]
```

`protocol.recv_exactly()` repeatedly calls `recv()` until the requested
number of bytes has arrived.

### File metadata payload

The metadata payload is binary:

```text
transfer_id       16 bytes (UUID)
filename_length    1 byte
filename          UTF-8 bytes
file_size         8 bytes, network byte order
chunk_size        4 bytes, network byte order
```

The filename length is measured in encoded UTF-8 bytes, not Python
characters.

### Transfer flow

```text
1. Client sends framed file metadata.
2. Interactive server asks the receiver to accept or reject.
3. Server sends acceptance or failure.
4. Server requests hashes for retained chunks when resuming.
5. Client sends the requested chunk hashes.
6. Server sends START_TRANSFER or RESUME_TRANSFER with an offset.
7. Client streams file bytes from that offset.
8. Client sends a framed SHA-256 digest.
9. Server verifies the digest and file size.
10. Server atomically renames the .part file to the final output.
11. Server sends TRANSFER_COMPLETE or TRANSFER_FAILED.
```

The file data itself is not wrapped in one message. Its exact length is
defined by the metadata and resume offset.

### Message types

| Value | Meaning |
| --- | --- |
| `1` | Start transfer |
| `2` | Resume transfer |
| `3` | Hash request |
| `4` | Hash response |
| `5` | Transfer complete |
| `6` | Transfer failed |
| `7` | Transfer accepted |

### Resume state

Interrupted transfers use:

```text
<transfer-id>.part
<transfer-id>.meta
```

The metadata file prevents a different file from reusing an existing partial
transfer. The receiver validates retained complete chunks using SHA-256
hashes supplied by the sender. Any corrupted suffix is discarded before
resuming.

The transfer ID is stable in the command-line client for an unchanged source
file. It is derived from the absolute path, file size, and modification time.

## 4. File and Integrity Safety

Files are streamed in chunks and are never loaded into memory in full.
The normal client chunk size is 64 KB. The `send_file()` API keeps the chunk
size configurable for tests and experiments, but it remains fixed during one
transfer so resume chunk boundaries remain valid.

Received filenames are rejected if they contain:

- Absolute paths.
- Directory components.
- Parent-directory traversal.
- NUL characters.
- Invalid or empty names.

An existing destination file is not overwritten; the transfer is rejected.

The server writes to a `.part` file and publishes the final file only after:

- The expected number of bytes has been received.
- The SHA-256 digest matches.
- The final file size matches the metadata.

Old resume state is removed after its retention period. Explicit receiver
rejection also removes existing `.part` and `.meta` files for that transfer.

## 5. Concurrency

`serve()` accepts connections continuously:

```text
accept client A -> worker A
accept client B -> worker B
accept client C -> worker C
```

Each worker owns its socket, checksum state, metadata, and transfer files.
Receiver prompts are protected by a lock so concurrent workers do not read
terminal input simultaneously.

The server uses a 30-second network operation timeout. Receiver approval has
a separate 120-second timeout because it requires human input. The client
waits 150 seconds for the approval response.

## 6. Error Handling

The implementation distinguishes several failure categories:

- Invalid metadata or unsafe filenames.
- Unsupported or malformed protocol messages.
- Connection closure or reset.
- Socket timeout.
- Checksum mismatch.
- Metadata mismatch during resume.
- Filesystem and startup errors.

An interrupted transfer retains resume state. A checksum failure or completed
rejection does not publish corrupted data.

## 7. Testing

Run all tests with:

```bash
python -m unittest discover -s tests -q
```

Unit tests:

```text
tests/test_checksum.py
tests/test_protocol.py
```

Integration tests:

```text
tests/test_transfer.py
tests/test_integration.py
```

The tests cover protocol framing, binary and empty files, Unicode names,
unsafe paths, checksum failures, timeouts, interrupted transfers, resume
repair, rejection cleanup, concurrent transfers, and the UDP-discovery to
TCP-transfer workflow.

## 8. Known Limitations

- Authentication and TLS are intentionally not implemented.
- The application assumes a trusted local network.
- Discovery depends on UDP broadcast and firewall configuration.
- The client currently selects one discovered device per transfer.
- Graceful shutdown is not implemented.
- The command-line interface is intentionally simple.
- Android and desktop GUI clients are future consumers of the protocol.

## 9. Future Evolution

The core learning project is complete. Possible future work includes:

1. Cross-platform testing on macOS and Windows.
2. Graceful shutdown for active worker threads.
3. Better device selection and transfer history.
4. Authentication and encrypted transport.
5. A desktop GUI using structured progress events.
6. An Android client implementing the same language-independent protocol.
