"""Addresses a phone on the same Wi-Fi can use to reach this computer."""
import socket


def lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))  # no packet is sent; this only picks the outgoing interface
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith('127.'):
                ips.append(ip)
    except OSError:
        pass
    return ips


def public_base(request):
    """Base URL for links and QR codes. 'localhost' means nothing to a phone, so swap in the LAN address."""
    url = request.url
    host = url.hostname or 'localhost'
    if host in ('localhost', '127.0.0.1', '::1'):
        ips = lan_ips()
        if ips:
            host = ips[0]
    port = f':{url.port}' if url.port else ''
    return f'{url.scheme}://{host}{port}/'


def is_loopback_only(request):
    return (request.url.hostname or '') in ('localhost', '127.0.0.1', '::1')
