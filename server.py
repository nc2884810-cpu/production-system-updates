from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

PORT = 8000

class ReusableTCPServer(TCPServer):
    allow_reuse_address = True

class MyHandler(SimpleHTTPRequestHandler):
    pass

with ReusableTCPServer(("", PORT), MyHandler) as server:
    print("Сервер запущен:")
    print(f"http://localhost:{PORT}")
    print("Для остановки нажмите Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nСервер остановлен.")
