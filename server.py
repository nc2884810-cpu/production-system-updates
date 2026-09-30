from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = ""
PORT = 8000
ROOT = Path(__file__).resolve().parent


class ProductionHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        # Браузер перепроверяет изменённые файлы после обновления,
        # но может использовать локальную копию, если файл не менялся.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format, *args):
        print(f"[HTTP] {self.address_string()} - {format % args}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), ProductionHandler)
    server.daemon_threads = True

    print("Сервер запущен:")
    print(f"http://localhost:{PORT}")
    print("Для остановки нажмите Ctrl+C")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nСервер остановлен.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
