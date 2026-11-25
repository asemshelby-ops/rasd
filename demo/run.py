"""Starts the demo on this laptop so that phones on the same hotspot can open it.

    python -m demo.run            https on port 8443: phones can record voice notes
    python -m demo.run --http     plain http on port 8000: phones can type and attach, not record

With https the laptop makes its own certificate (demo/cert/). Each phone shows
a warning the first time it opens the address: choose "Advanced", then
"Proceed". That is expected, and it is needed once per phone.
"""

import argparse
import socket
from pathlib import Path

CERT_DIR = Path(__file__).resolve().parent / "cert"


def local_addresses() -> list[str]:
    """The addresses of this laptop on its networks (the hotspot gives it one)."""
    found = []
    try:  # the address used to reach other machines; connecting a UDP socket sends nothing
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    return [ip for ip in dict.fromkeys(found) if not ip.startswith("127.")]


def address_lines(addresses: list[str], port: int, https: bool) -> list[str]:
    """What to print: the pages to open on the laptop and on the phones."""
    scheme = "https" if https else "http"
    lines = [
        "Rasd demo is starting.",
        "",
        "On this laptop (the big screen):",
        f"  {scheme}://localhost:{port}/board",
        "",
    ]
    if not addresses:
        lines += ["No network address was found. Connect the laptop to the phone hotspot and start again."]
    for ip in addresses:
        lines += [
            f"On the phones (same hotspot), address {ip}:",
            f"  report page:   {scheme}://{ip}:{port}/report",
            f"  operator page: {scheme}://{ip}:{port}/operator   (the replay switch)",
            f"  scenario card: {scheme}://{ip}:{port}/scenario-card",
            "",
        ]
    if https:
        lines += ["The first time, each phone shows a certificate warning: choose Advanced, then Proceed."]
    else:
        lines += ["Plain http: phones cannot record voice notes on this connection. They can type, or attach a sound file."]
    lines += ["Stop with Ctrl+C."]
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Rasd demo for phones on the same hotspot.")
    parser.add_argument("--http", action="store_true", help="plain http on port 8000 (phones cannot record)")
    parser.add_argument("--port", type=int, default=None)
    options = parser.parse_args()

    import uvicorn

    https = not options.http
    port = options.port or (8443 if https else 8000)
    addresses = local_addresses()
    extra = {}
    if https:
        from demo.certificate import certificate_covers, make_certificate

        if not certificate_covers(CERT_DIR, addresses):
            make_certificate(CERT_DIR, addresses)
            print(f"Made a new certificate for: localhost {' '.join(addresses)}")
        extra = {"ssl_certfile": str(CERT_DIR / "cert.pem"), "ssl_keyfile": str(CERT_DIR / "key.pem")}
    print("\n".join(address_lines(addresses, port, https)))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="warning", **extra)


if __name__ == "__main__":
    main()
