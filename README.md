# Offline File Transfer

An educational peer-to-peer file-transfer application built with Python
standard-library networking APIs. Devices discover each other on a local
network, establish a TCP connection, and transfer files with integrity
verification and resume support.

## Features

- UDP broadcast device discovery.
- Dynamic TCP port allocation.
- Receiver approval before a transfer begins.
- Concurrent transfers using one worker thread per connection.
- Length-prefixed application-level TCP framing.
- Streaming binary file transfer without loading the whole file into memory.
- Configurable transfer chunk size through the Python API.
- SHA-256 integrity verification.
- Resume support for interrupted transfers.
- Safe filename validation.
- Existing destination files are not overwritten.
- Expiration of old resume state.
- Unit and integration tests.

## Requirements

- Python 3.10 or newer.
- Devices connected to the same local network.
- UDP discovery traffic allowed by the local firewall.

The application uses only the Python standard library.

## Running the server

Start the receiver:

```bash
python server.py
```

The server:

1. Asks the operating system for a free TCP port.
2. Starts UDP discovery using the actual TCP port.
3. Waits for file-transfer clients.
4. Asks the receiver to accept or reject each transfer.
5. Stores completed files in `received/`.

Optional configuration:

```bash
python server.py \
  --port 8080 \
  --output-dir downloads \
  --device-name MyLaptop \
  --discovery-port 37020 \
  --timeout 30
```

Use `--port 0` to let the operating system select a free TCP port. This is
the default.

## Running the client

Run interactively:

```bash
python client.py
```

Or provide the file path directly:

```bash
python client.py /path/to/file.zip
```

The client discovers available devices, displays their names, IP addresses,
and TCP ports, and asks which device should receive the file.

## Architecture

```text
Client
  |
  | UDP discovery
  v
Device information
  |
  | TCP connection
  v
Receiver approval decision
  |
  | framed metadata and binary data
  v
Streaming receiver
  |
  v
SHA-256 verification and atomic publication
```

Main modules:

| File | Responsibility |
| --- | --- |
| `client.py` | File selection, discovery, sending, resume coordination |
| `server.py` | TCP listener, worker threads, approval, receiving |
| `discovery.py` | UDP discovery request and response handling |
| `protocol.py` | Binary framing and transfer message encoding |
| `utils.py` | Filename validation, formatting, cleanup, filesystem helpers |
| `progress.py` | Terminal progress rendering |
| `checksum.py` | Constant-time digest comparison |

## Protocol overview

### UDP discovery

The client broadcasts a discovery request on UDP port `37020`.

The receiver responds with a small JSON message containing:

- Discovery message type.
- Discovery protocol version.
- Device name.
- TCP transfer port.

The sender obtains the receiver IP address from the UDP packet's source
address. The payload supplies the TCP port.

### TCP transfer

TCP is treated as a byte stream, so application-level length-prefix framing
is used for control messages.

The transfer flow is:

```text
Metadata
  -> Receiver approval
  -> Optional resume hash request
  -> Transfer status and offset
  -> Streamed file bytes
  -> Sender SHA-256 digest
  -> Receiver verification
  -> Completion or failure result
```

Partial transfers are stored as:

```text
<transfer-id>.part
<transfer-id>.meta
```

The final file is published only after the received size and SHA-256 digest
match the sender's metadata.

## Testing

Run all tests:

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

The tests cover empty and binary files, Unicode filenames, malformed
messages, unsafe filenames, checksum failures, timeouts, interrupted
transfers, resume repair, rejection cleanup, concurrent transfers, and the
UDP-discovery-to-TCP-transfer workflow.

## Intentional limitations

- Authentication and TLS are not implemented; this is a trusted-LAN
  educational prototype.
- Graceful shutdown is not implemented.
- The client currently selects one discovered device for each transfer.
- Discovery depends on local-network broadcast and firewall configuration.
- The command-line interface is intentionally simple.
- Android and GUI clients are future projects built on the same protocol.

## Learning goals

This project demonstrates:

- TCP socket lifecycle and byte-stream behavior.
- UDP discovery and LAN communication.
- Application-level protocol framing.
- Streaming file I/O and chunking.
- Checksums and data integrity.
- Resume offsets and transfer state.
- Concurrent connection handling.
- Failure handling and integration testing.
