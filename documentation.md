# Offline File Transfer - Project Documentation

This documentation serves as a comprehensive guide to the **Offline File Transfer Application**, explaining its current architecture, underlying networking fundamentals, protocol specifications, security analysis, and planned development roadmap.

---

## 1. Project Overview & Architecture

The Offline File Transfer Application is a production-quality, offline-first system designed to transfer files directly between nearby devices on a local network (LAN) without requiring internet access. It leverages direct TCP connections over socket interfaces to facilitate highly efficient, stream-based transfers.

### Current High-Level Design
The system uses a classic **Client-Server Architecture**:
1. **Server (`server.py`)**: Acts as a passive receiver. It binds to a port and listens for an incoming connection from a client.
2. **Client (`client.py`)**: Acts as an active sender. It initiates a connection to the server's IP address and port, and then transmits the file.

```text
       [Client: client.py]                      [Server: server.py]
      (Initiates Connection)                   (Binds & Listens to 8080)
               │                                           │
               ├─────────────── TCP Handshake ────────────>│
               │                                           │
               ├─────── 1. Filename Length (4 Bytes) ─────>│ (Reads 4 bytes, unpacks)
               ├─────── 2. Filename (UTF-8 Bytes) ────────>│ (Reads N bytes, decodes)
               ├─────── 3. File Size (8 Bytes) ───────────>│ (Reads 8 bytes, unpacks)
               │                                           │
               ├─────── 4. File Content (Chunks) ─────────>│ (Reads chunks, writes to disk)
               │           [CHUNK_SIZE = 4096]             │
               │                                           │
               X ───────────── Close Connection ───────────X (Clean cleanup)
```

---

## 2. Protocol Specification (Phase 2 Current Design)

TCP is a **byte stream protocol**, meaning it has no inherent concept of message boundaries. To prevent messages from coalescing or fragmenting unexpectedly, the application implements an explicit framing protocol over the stream:

### 2.1 Message Frame Structure

| Field Name | Type / Size | Endianness | Description |
| :--- | :--- | :--- | :--- |
| **Filename Length** | 4-byte unsigned integer (`uint32`) | Big-Endian (`!I`) | Tells the server how many bytes to read for the filename. |
| **Filename** | variable-length byte string | UTF-8 | The actual raw name of the file (e.g. `test.txt`). |
| **File Size** | 8-byte unsigned integer (`uint64`) | Big-Endian (`!Q`) | Specifies the total length of the file payload in bytes. |
| **File Data** | Stream of binary chunks | Raw binary stream | The actual file contents, read and transmitted in chunks of 4096 bytes. |

### 2.2 Why Big-Endian (`!`) is Vital
In network programming, different CPU architectures represent integers differently (Little-Endian vs. Big-Endian). 
* **Big-Endian** (Most Significant Byte first) is the standardized **Network Byte Order**.
* Using Python's `struct` library with the `!` prefix (e.g., `struct.pack("!I", length)`) ensures that metadata is serialized uniformly, allowing devices with different hardware architectures (e.g., an Intel x86 PC and an ARM-based phone/mac) to exchange numeric lengths reliably without corruption.

---

## 3. Deep-Dive: Core Networking & Socket Concepts

To master socket programming, it is crucial to understand how the operating system handles networking under the hood:

### 3.1 Socket States & Core System Calls
- **`socket()`**: Requests the operating system kernel to allocate a network socket descriptor. 
  - `socket.AF_INET`: Specifies IPv4 addressing.
  - `socket.SOCK_STREAM`: Specifies the TCP transmission protocol (guaranteeing reliable, ordered delivery).
- **`bind(address, port)`**: (Server-side) Associates the socket with a specific network interface IP and port number.
  - **`0.0.0.0`**: Binds the server to **all available network interfaces** on the host. This allows any device on the local network (as well as localhost `127.0.0.1`) to connect.
  - **`127.0.0.1`**: Binds the socket only to the loopback interface, restricting connections to the same machine.
- **`listen(backlog)`**: Places the bound socket into a passive state, ready to accept incoming connection requests. The `backlog` parameter specifies the queue size for pending connections.
- **`connect(address, port)`**: (Client-side) Initiates the TCP three-way handshake with the listening server.
- **`accept()`**: Blocks the server program execution until a client connects. Once connected, it returns a **new socket object** dedicated specifically to that client, along with the client's network address. The original server socket continues listening for new connections.
- **`sendall(data)`**: High-level routine that ensures all provided bytes are pushed onto the OS TCP buffer, handling potential partial sends internally.
- **`recv(bufsize)`**: Receives data from the socket. It is non-blocking or blocking depending on configuration, and returns up to `bufsize` bytes.

### 3.2 The Stream Assembly Problem: `recv_exactly`
Because TCP is stream-oriented, a call to `recv(100)` is not guaranteed to return 100 bytes, even if the sender sent exactly 100 bytes. It might return 10, 50, or 100 bytes depending on network congestion, fragmentation, and OS buffer availability.

To solve this, our application implements `recv_exactly(sock, size)`:
```python
def recv_exactly(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Connection closed unexpectedly")
        data += chunk
    return data
```
This loop explicitly guarantees that the server blocks and reads until *exactly* the requested metadata bytes have arrived, preventing protocol misalignment.

---

## 4. Current Implementation Critique (Analysis & Security)

While our initial implementation achieves basic TCP file transfer, it has several critical design gaps that we will address in subsequent development phases:

### 4.1 Security Vulnerabilities
1. **Path Traversal Attack**: 
   - **Vulnerability**: The server saves files using `"received_" + filename`. If a malicious client sends a filename like `../../etc/cron.d/malicious_job` or `..\..\..\AppData\Startup\backdoor.bat`, the server would write the file outside the intended download directory, potentially overwriting critical system files.
   - **Remediation**: Implement filename sanitization using `os.path.basename()` on the receiver side, and ensure the resolved path remains strictly within an designated downloads directory.
2. **Plaintext / No Authentication**:
   - **Vulnerability**: Anyone on the local network can connect to the server and send files, leading to denial of service, disk-space exhaustion, or malicious code injection.
   - **Remediation**: Phase 5 (Authentication challenge-response or pairing codes).
3. **No Transport Encryption**:
   - **Vulnerability**: Files and metadata are transferred in plain text over the wire, allowing eavesdroppers to reconstruct the files.

### 4.2 Engineering & Robustness Limits
1. **Single-threaded (No Concurrency)**: The server accepts one connection, transfers one file, and then terminates. It cannot handle concurrent transfers or multiple devices.
2. **No Data Integrity Validation**: If a byte is flipped during transmission or the connection drops halfway, the server might save a corrupted file without notifying the user.
3. **No Resume Capabilities**: Interrupted transfers require starting from the very beginning, wasting bandwidth and time on large files.

---

## 5. Roadmap & Evolutionary Path

Consistent with `gemini.md`, we will evolve this codebase along the following incremental roadmap:

1. **Phase 2.1 (Robustness & Filename Security)**: 
   - Refactor client and server to sanitize paths and handle filesystem errors (e.g. disk full, permission denied).
2. **Phase 3 (Data Integrity)**:
   - Introduce SHA-256 validation. The sender computes the hash of the file, sends it in the metadata, and the receiver verifies it after the transfer.
3. **Phase 3.1 (Structured JSON Header)**:
   - Instead of manual field-by-field stream unpacking, transition to sending a fixed-size integer representing the length of a JSON header, followed by the JSON string itself, and then the binary payload. This makes the protocol highly extensible (allowing us to easily add checksums, custom metadata, and resume offsets).
4. **Phase 4 & 6 (Discovery & Concurrency)**:
   - Add background thread UDP discovery and transition the TCP server to handle multiple connections asynchronously (`asyncio` or ThreadPool).
