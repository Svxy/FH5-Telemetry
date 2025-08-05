import socket

ip = "0.0.0.0"
port = 5607

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((ip, port))
sock.settimeout(10)

print(f"listening on {ip}:{port}...")

try:
    while True:
        data, addr = sock.recvfrom(2048)
        print(f"from {addr}: {len(data)} bytes")
except socket.timeout:
    print("no data received.")