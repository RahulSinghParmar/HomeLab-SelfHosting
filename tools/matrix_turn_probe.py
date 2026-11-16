"""Secret-free external STUN reachability probe for an optional TURN service."""
from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys


MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_SUCCESS = 0x0101
MAPPED_ADDRESS = 0x0001
XOR_MAPPED_ADDRESS = 0x0020


def request() -> tuple[bytes, bytes]:
    transaction = os.urandom(12)
    return struct.pack("!HHI12s", BINDING_REQUEST, 0, MAGIC_COOKIE,
                       transaction), transaction


def mapped_family(message: bytes, transaction: bytes) -> str:
    if len(message) < 20:
        raise ValueError("short STUN response")
    message_type, length, cookie, returned = struct.unpack(
        "!HHI12s", message[:20])
    if message_type != BINDING_SUCCESS or cookie != MAGIC_COOKIE:
        raise ValueError("unexpected STUN response")
    if returned != transaction:
        raise ValueError("STUN transaction mismatch")
    if len(message) < 20 + length:
        raise ValueError("truncated STUN attributes")
    offset = 20
    while offset + 4 <= 20 + length:
        attribute, size = struct.unpack("!HH", message[offset:offset + 4])
        value = message[offset + 4:offset + 4 + size]
        if attribute in (MAPPED_ADDRESS, XOR_MAPPED_ADDRESS) and len(value) >= 4:
            family = value[1]
            if family == 0x01:
                return "ipv4"
            if family == 0x02:
                return "ipv6"
            raise ValueError("unknown mapped-address family")
        offset += 4 + ((size + 3) // 4) * 4
    raise ValueError("STUN response omitted a mapped address")


def probe(host: str, port: int, transport: str,
          timeout: float) -> dict:
    packet, transaction = request()
    family, socket_type = socket.AF_UNSPEC, (
        socket.SOCK_DGRAM if transport == "udp" else socket.SOCK_STREAM)
    candidates = socket.getaddrinfo(host, port, family, socket_type)
    errors = []
    for address_family, kind, protocol, _, address in candidates:
        try:
            with socket.socket(address_family, kind, protocol) as client:
                client.settimeout(timeout)
                if transport == "udp":
                    client.sendto(packet, address)
                    response, _ = client.recvfrom(4096)
                else:
                    client.connect(address)
                    client.sendall(packet)
                    response = client.recv(4096)
                return {
                    "kind": "homelab-matrix-turn-stun-probe",
                    "contract": "phase7-matrix-integration-v1",
                    "host": host,
                    "port": port,
                    "transport": transport,
                    "dns_resolved": True,
                    "binding_success": True,
                    "mapped_address_present": True,
                    "mapped_family": mapped_family(response, transaction),
                    "address_value_disclosed": False,
                    "credential_used": False,
                }
        except (OSError, ValueError) as error:
            errors.append(type(error).__name__)
    raise RuntimeError("STUN probe failed for every resolved address: "
                       + ",".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe a public TURN listener using a credential-free STUN binding")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=3478)
    parser.add_argument("--transport", choices=("udp", "tcp"), default="udp")
    parser.add_argument("--timeout", type=float, default=8.0)
    arguments = parser.parse_args()
    if not 1 <= arguments.port <= 65535 or not 0.1 <= arguments.timeout <= 60:
        parser.error("invalid port or timeout")
    try:
        result = probe(arguments.host, arguments.port, arguments.transport,
                       arguments.timeout)
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({
            "kind": "homelab-matrix-turn-stun-probe",
            "contract": "phase7-matrix-integration-v1",
            "host": arguments.host,
            "port": arguments.port,
            "transport": arguments.transport,
            "binding_success": False,
            "address_value_disclosed": False,
            "credential_used": False,
            "error_class": type(error).__name__,
        }, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
