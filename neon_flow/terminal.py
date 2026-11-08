"""Read-only relay of one Maestri terminal (Wire websocket -> Server-Sent Events).

The browser only receives output and geometry; the token stays on this machine and nothing is ever
written to the terminal (only websocket control frames: pong and keepalive ping)."""
import base64
import hashlib
import json
import secrets
import select
from urllib.parse import urlencode
from uuid import UUID


def stream_terminal(handler, terminal_id):
    from .wire import _tls, credentials

    terminal_id = str(UUID(terminal_id))
    saved, token = credentials()
    sock = _tls(saved['host'], saved['port'], saved['serverKeyHash'])
    started = False
    try:
        key = base64.b64encode(secrets.token_bytes(16)).decode('ascii')
        path = f'/api/terminals/{terminal_id}/stream?' + urlencode({'token': token})
        sock.sendall((f'GET {path} HTTP/1.1\r\nHost: {saved["host"]}:{saved["port"]}\r\n'
                      f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                      'Sec-WebSocket-Version: 13\r\n\r\n').encode('ascii'))
        with sock.makefile('rb', buffering=0) as source:
            status = source.readline(4096)
            headers = {}
            for _ in range(64):
                line = source.readline(4096)
                if line in (b'\r\n', b'\n', b''):
                    break
                name, _, value = line.decode('ascii', 'replace').partition(':')
                headers[name.lower()] = value.strip()
            expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if not status.startswith(b'HTTP/1.1 101 ') or headers.get('sec-websocket-accept') != expected:
                raise RuntimeError('O Maestri não disponibilizou o terminal completo.')
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/event-stream')
            handler.send_header('Cache-Control', 'no-store')
            handler.send_header('X-Content-Type-Options', 'nosniff')
            handler.end_headers()
            started = True

            def read(size):
                chunks = bytearray()
                while len(chunks) < size:
                    chunk = source.read(size - len(chunks))
                    if not chunk:
                        raise ConnectionError('Terminal desconectado.')
                    chunks.extend(chunk)
                return bytes(chunks)

            def control(opcode, payload=b''):
                mask = secrets.token_bytes(4)
                sock.sendall(bytes([0x80 | opcode, 0x80 | len(payload)]) + mask
                             + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

            pending = bytearray()
            message_opcode = None
            while True:
                if not sock.pending() and not select.select([sock], [], [], 10)[0]:
                    control(9)
                    handler.wfile.write(b': keepalive\n\n')
                    handler.wfile.flush()
                    continue
                first, second = read(2)
                opcode, size = first & 15, second & 127
                if second & 128:
                    raise ValueError('Frame Wire inesperado.')
                if size == 126:
                    size = int.from_bytes(read(2), 'big')
                elif size == 127:
                    size = int.from_bytes(read(8), 'big')
                if size > 8 * 1024 * 1024 or len(pending) + size > 8 * 1024 * 1024:
                    raise ValueError('Saída do terminal excede 8 MiB por mensagem.')
                payload = read(size)
                if opcode == 8:
                    return
                if opcode == 9:
                    if len(payload) > 125:
                        raise ValueError('Ping Wire inválido.')
                    control(10, payload)
                    continue
                if opcode == 10:
                    continue
                if opcode in (1, 2):
                    message_opcode = opcode
                elif opcode != 0 or message_opcode is None:
                    raise ValueError('Mensagem Wire inválida.')
                pending.extend(payload)
                if not first & 128:
                    continue
                if message_opcode == 2:
                    event = {'type': 'output', 'data': base64.b64encode(pending).decode('ascii')}
                else:
                    message = json.loads(pending)
                    event = {k: message[k] for k in ('type', 'cols', 'rows') if k in message}
                handler.wfile.write(b'data: ' + json.dumps(event).encode('utf-8') + b'\n\n')
                handler.wfile.flush()
                pending.clear()
                message_opcode = None
    except Exception:
        if not started:
            raise
        try:
            handler.wfile.write(b'data: {"type":"error","message":"Fluxo interrompido. Feche e reabra o terminal."}\n\n')
            handler.wfile.flush()
        except OSError:
            pass
    finally:
        sock.close()
