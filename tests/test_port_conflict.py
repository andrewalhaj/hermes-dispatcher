"""Tests for graceful port-conflict handling in the dispatcher entrypoint.

These exercise the bind-resolution helpers in server.py against real sockets,
without starting uvicorn. Run: ./.venv/bin/python -m pytest tests/test_port_conflict.py -q
"""
import logging
import socket

import server

log = logging.getLogger("test")


def _occupy(host: str) -> tuple[socket.socket, int]:
    """Bind an ephemeral port and keep it listening; return (sock, port)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    s.listen(1)
    return s, s.getsockname()[1]


def test_parse_fallback_ports_list_range_and_dedup():
    assert server._parse_fallback_ports("8788,8790,8800-8802,8790") == [
        8788, 8790, 8800, 8801, 8802
    ]
    assert server._parse_fallback_ports("") == []
    assert server._parse_fallback_ports("  , bad , 9000 ") == [9000]


def test_can_bind_true_for_free_port():
    # Find a free port, release it, then assert _can_bind agrees it's free.
    s, port = _occupy("127.0.0.1")
    s.close()
    assert server._can_bind("127.0.0.1", port) is True


def test_can_bind_false_for_occupied_port():
    s, port = _occupy("127.0.0.1")
    try:
        assert server._can_bind("127.0.0.1", port) is False
    finally:
        s.close()


def test_resolve_uses_primary_when_free():
    s, port = _occupy("127.0.0.1")
    s.close()
    chosen = server._resolve_bind_port(
        "127.0.0.1", port, retries=1, backoff=0.0, fallbacks=[], log=log
    )
    assert chosen == port


def test_resolve_falls_back_when_primary_busy():
    busy_sock, busy_port = _occupy("127.0.0.1")
    free_sock, free_port = _occupy("127.0.0.1")
    free_sock.close()  # free_port is now available
    try:
        chosen = server._resolve_bind_port(
            "127.0.0.1", busy_port, retries=1, backoff=0.0,
            fallbacks=[free_port], log=log,
        )
        assert chosen == free_port
    finally:
        busy_sock.close()


def test_resolve_returns_none_when_all_busy():
    s1, p1 = _occupy("127.0.0.1")
    s2, p2 = _occupy("127.0.0.1")
    try:
        chosen = server._resolve_bind_port(
            "127.0.0.1", p1, retries=2, backoff=0.0, fallbacks=[p2], log=log
        )
        assert chosen is None
    finally:
        s1.close()
        s2.close()


def test_port_holder_never_raises():
    # Whatever the privilege level, this must return a str and not blow up.
    s, port = _occupy("127.0.0.1")
    try:
        assert isinstance(server._port_holder("127.0.0.1", port), str)
    finally:
        s.close()
