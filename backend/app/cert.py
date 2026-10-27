"""Makes a self-signed HTTPS certificate so phones on the same Wi-Fi can use the camera and GPS
(browsers only allow both on https:// pages). Run: python -m app.cert"""
import datetime
import ipaddress
import os
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from .db import STORE_DIR
from .net import lan_ips

CERT_DIR = os.path.join(STORE_DIR, 'certs')
KEY = os.path.join(CERT_DIR, 'key.pem')
CERT = os.path.join(CERT_DIR, 'cert.pem')
STAMP = os.path.join(CERT_DIR, 'ips.txt')


def ensure():
    os.makedirs(CERT_DIR, exist_ok=True)
    ips = sorted(set(lan_ips() + ['127.0.0.1']))
    if os.path.exists(CERT) and os.path.exists(STAMP) and open(STAMP).read() == ','.join(ips):
        return ips  # still valid for this network
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Pramaan demo (self-signed)')])
    san = [x509.DNSName('localhost'), x509.DNSName(socket.gethostname())] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256()))
    with open(KEY, 'wb') as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    with open(CERT, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(STAMP, 'w') as f:
        f.write(','.join(ips))
    return ips


if __name__ == '__main__':
    ips = ensure()
    print('HTTPS certificate ready.')
    for ip in ips:
        if not ip.startswith('127.'):
            print(f'  On a phone on the same Wi-Fi, open:  https://{ip}:8443')
    print('  On this computer:                    https://localhost:8443')
    print('  The browser will warn that the certificate is self-signed: choose Advanced, then Proceed.')
