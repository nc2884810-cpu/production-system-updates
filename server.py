from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import threading
import uuid

HOST = ""
PORT = 8000
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_FILE = DATA_DIR / "production_records.json"
DATA_LOCK = threading.Lock()
MAX_REQUEST_SIZE = 1024 * 1024


def ensure_data_file():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]\n", encoding="utf-8")


def read_records_unlocked():
    if not DATA_FILE.exists():
        return []

    text = DATA_FILE.read_text(encoding="utf-8").strip()

    if not text:
        return []

    records = json.loads(text)

    if not isinstance(records, list):
        raise ValueError("Файл данных имеет неверный формат.")

    return records


def write_records_unlocked(records):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_file = DATA_FILE.with_suffix(".json.tmp")
    content = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    temporary_file.write_text(content, encoding="utf-8")
    os.replace(temporary_file, DATA_FILE)


def parse_integer(value, field_name, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"Поле «{field_name}» должно быть целым числом.")

    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Поле «{field_name}» должно быть целым числом.")

    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"Поле «{field_name}» должно быть целым числом.")

    if number < minimum:
        raise ValueError(
            f"Поле «{field_name}» должно быть не меньше {minimum}."
        )

    return number


def validate_record(payload):
    if not isinstance(payload, dict):
        raise ValueError("Ожидался JSON-объект.")

    product_name = str(payload.get("productName", "")).strip()
    defect_reason = str(payload.get("defectReason", "")).strip()

    if not product_name:
        raise ValueError("Укажите изделие.")

    if len(product_name) > 200:
        raise ValueError("Название изделия слишком длинное.")

    if len(defect_reason) > 2000:
        raise ValueError("Описание причины брака слишком длинное.")

    quantity = parse_integer(payload.get("quantity"), "Количество", 1)
    good_quantity = parse_integer(payload.get("goodQuantity"), "Годных", 0)
    defect_quantity = parse_integer(payload.get("defectQuantity"), "Брак", 0)

    if good_quantity + defect_quantity != quantity:
        raise ValueError(
            "Годных + брак должны быть равны общему количеству."
        )

    defect_percent = (defect_quantity / quantity) * 100

    return {
        "id": str(uuid.uuid4()),
        "date": datetime.now(timezone.utc).isoformat(),
        "productName": product_name,
        "quantity": quantity,
        "goodQuantity": good_quantity,
        "defectQuantity": defect_quantity,
        "defectPercent": round(defect_percent, 4),
        "defectReason": defect_reason,
    }


class ProductionHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "no-cache")

        super().end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/records":
            self.handle_get_records()
            return

        super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/records":
            self.handle_create_record()
            return

        self.send_json(404, {"error": "API-адрес не найден."})

    def handle_get_records(self):
        try:
            with DATA_LOCK:
                records = read_records_unlocked()

            self.send_json(200, {"records": records})
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.send_json(
                500,
                {"error": f"Не удалось прочитать данные: {error}"},
            )

    def handle_create_record(self):
        try:
            payload = self.read_json_body()
            record = validate_record(payload)

            with DATA_LOCK:
                records = read_records_unlocked()
                records.insert(0, record)
                write_records_unlocked(records)

            self.send_json(201, {"record": record})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Некорректный JSON."})
        except OSError as error:
            self.send_json(
                500,
                {"error": f"Не удалось сохранить данные: {error}"},
            )

    def read_json_body(self):
        content_length = self.headers.get("Content-Length")

        if content_length is None:
            raise ValueError("Отсутствует Content-Length.")

        try:
            length = int(content_length)
        except ValueError:
            raise ValueError("Некорректный Content-Length.")

        if length <= 0:
            raise ValueError("Пустой запрос.")

        if length > MAX_REQUEST_SIZE:
            raise ValueError("Запрос слишком большой.")

        raw_data = self.rfile.read(length)
        return json.loads(raw_data.decode("utf-8"))

    def send_json(self, status_code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(status_code)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"[HTTP] {self.address_string()} - {format % args}")


def main():
    ensure_data_file()

    server = ThreadingHTTPServer((HOST, PORT), ProductionHandler)
    server.daemon_threads = True

    print("Сервер запущен:")
    print(f"http://localhost:{PORT}")
    print(f"Файл данных: {DATA_FILE}")
    print("Для остановки нажмите Ctrl+C")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
