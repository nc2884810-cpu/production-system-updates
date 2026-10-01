from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
import json
import sqlite3

HOST = ""
PORT = 8000
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_FILE = DATA_DIR / "production.db"
LEGACY_JSON_FILE = DATA_DIR / "production_records.json"
MAX_REQUEST_SIZE = 1024 * 1024
MIGRATION_KEY = "json_migration_v1"

SORT_SQL = {
    "date_desc": "date DESC, id DESC",
    "date_asc": "date ASC, id ASC",
    "quantity_desc": "quantity DESC, id DESC",
    "quantity_asc": "quantity ASC, id DESC",
    "defect_desc": "(CAST(defect_quantity AS REAL) / quantity) DESC, id DESC",
    "defect_asc": "(CAST(defect_quantity AS REAL) / quantity) ASC, id DESC",
}


class RecordNotFoundError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def connect_db():
    connection = sqlite3.connect(DB_FILE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with connect_db() as connection:
        connection.execute("PRAGMA journal_mode = WAL")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS production_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                good_quantity INTEGER NOT NULL CHECK (good_quantity >= 0),
                defect_quantity INTEGER NOT NULL CHECK (defect_quantity >= 0),
                defect_reason TEXT NOT NULL DEFAULT '',
                CHECK (good_quantity + defect_quantity = quantity)
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

    migrate_legacy_json()


def parse_integer(value, field_name, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"Поле «{field_name}» должно быть целым числом.")

    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"Поле «{field_name}» должно быть целым числом.")

    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Поле «{field_name}» должно быть целым числом.")

    if number < minimum:
        raise ValueError(
            f"Поле «{field_name}» должно быть не меньше {minimum}."
        )

    return number


def validate_record_payload(payload):
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

    return {
        "productName": product_name,
        "quantity": quantity,
        "goodQuantity": good_quantity,
        "defectQuantity": defect_quantity,
        "defectReason": defect_reason,
    }


def validate_date_filter(value, field_name):
    if not value:
        return ""

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(
            f"Фильтр «{field_name}» должен иметь формат ГГГГ-ММ-ДД."
        )

    return value


def first_query_value(query, key, default=""):
    values = query.get(key)
    return values[0] if values else default


def parse_filters(query):
    search = first_query_value(query, "search").strip()
    date_from = validate_date_filter(
        first_query_value(query, "date_from"),
        "Дата с",
    )
    date_to = validate_date_filter(
        first_query_value(query, "date_to"),
        "Дата по",
    )
    sort = first_query_value(query, "sort", "date_desc")
    defect_only = first_query_value(query, "defect_only") == "1"

    if len(search) > 200:
        raise ValueError("Строка поиска слишком длинная.")

    if date_from and date_to and date_from > date_to:
        raise ValueError("Дата «с» не может быть позже даты «по».")

    if sort not in SORT_SQL:
        raise ValueError("Неизвестный вариант сортировки.")

    return {
        "search": search,
        "date_from": date_from,
        "date_to": date_to,
        "sort": sort,
        "defect_only": defect_only,
    }


def row_to_record(row):
    quantity = row["quantity"]
    defect_quantity = row["defect_quantity"]
    defect_percent = (
        (defect_quantity / quantity) * 100 if quantity > 0 else 0
    )

    return {
        "id": row["id"],
        "date": row["date"],
        "productName": row["product_name"],
        "quantity": quantity,
        "goodQuantity": row["good_quantity"],
        "defectQuantity": defect_quantity,
        "defectPercent": round(defect_percent, 4),
        "defectReason": row["defect_reason"],
    }


def select_record(connection, record_id):
    return connection.execute(
        """
        SELECT
            id,
            date,
            product_name,
            quantity,
            good_quantity,
            defect_quantity,
            defect_reason
        FROM production_records
        WHERE id = ?
        """,
        (record_id,),
    ).fetchone()


def build_filter_sql(filters):
    conditions = []
    params = []

    if filters["search"]:
        conditions.append("product_name LIKE ?")
        params.append(f'%{filters["search"]}%')

    if filters["date_from"]:
        conditions.append("substr(date, 1, 10) >= ?")
        params.append(filters["date_from"])

    if filters["date_to"]:
        conditions.append("substr(date, 1, 10) <= ?")
        params.append(filters["date_to"])

    if filters["defect_only"]:
        conditions.append("defect_quantity > 0")

    where_sql = (
        " WHERE " + " AND ".join(conditions)
        if conditions
        else ""
    )

    return where_sql, params


def get_records(filters):
    where_sql, params = build_filter_sql(filters)
    order_sql = SORT_SQL[filters["sort"]]

    with connect_db() as connection:
        total_count = connection.execute(
            "SELECT COUNT(*) AS count FROM production_records"
        ).fetchone()["count"]

        rows = connection.execute(
            f"""
            SELECT
                id,
                date,
                product_name,
                quantity,
                good_quantity,
                defect_quantity,
                defect_reason
            FROM production_records
            {where_sql}
            ORDER BY {order_sql}
            """,
            params,
        ).fetchall()

    return {
        "records": [row_to_record(row) for row in rows],
        "totalCount": total_count,
    }


def create_record(payload):
    record = validate_record_payload(payload)
    created_at = utc_now()

    with connect_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO production_records (
                date,
                product_name,
                quantity,
                good_quantity,
                defect_quantity,
                defect_reason
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                record["productName"],
                record["quantity"],
                record["goodQuantity"],
                record["defectQuantity"],
                record["defectReason"],
            ),
        )

        row = select_record(connection, cursor.lastrowid)

    return row_to_record(row)


def update_record(record_id, payload):
    record = validate_record_payload(payload)

    with connect_db() as connection:
        cursor = connection.execute(
            """
            UPDATE production_records
            SET
                product_name = ?,
                quantity = ?,
                good_quantity = ?,
                defect_quantity = ?,
                defect_reason = ?
            WHERE id = ?
            """,
            (
                record["productName"],
                record["quantity"],
                record["goodQuantity"],
                record["defectQuantity"],
                record["defectReason"],
                record_id,
            ),
        )

        if cursor.rowcount == 0:
            raise RecordNotFoundError(
                f"Запись №{record_id} не найдена."
            )

        row = select_record(connection, record_id)

    return row_to_record(row)


def delete_record(record_id):
    with connect_db() as connection:
        cursor = connection.execute(
            "DELETE FROM production_records WHERE id = ?",
            (record_id,),
        )

        if cursor.rowcount == 0:
            raise RecordNotFoundError(
                f"Запись №{record_id} не найдена."
            )


def metadata_value(connection, key):
    row = connection.execute(
        "SELECT value FROM app_metadata WHERE key = ?",
        (key,),
    ).fetchone()

    return row["value"] if row else None


def set_metadata(connection, key, value):
    connection.execute(
        """
        INSERT INTO app_metadata (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def migrate_legacy_json():
    with connect_db() as connection:
        if metadata_value(connection, MIGRATION_KEY) is not None:
            return

        existing_count = connection.execute(
            "SELECT COUNT(*) AS count FROM production_records"
        ).fetchone()["count"]

        if existing_count > 0:
            set_metadata(
                connection,
                MIGRATION_KEY,
                f"skipped_existing_database:{utc_now()}",
            )
            return

        if not LEGACY_JSON_FILE.exists():
            set_metadata(
                connection,
                MIGRATION_KEY,
                f"no_legacy_file:{utc_now()}",
            )
            return

        try:
            text = LEGACY_JSON_FILE.read_text(encoding="utf-8").strip()
            legacy_records = json.loads(text) if text else []
        except (OSError, json.JSONDecodeError) as error:
            print(f"[MIGRATION] JSON не перенесён: {error}")
            return

        if not isinstance(legacy_records, list):
            print("[MIGRATION] JSON не перенесён: ожидался список записей.")
            return

        migrated_count = 0
        skipped_count = 0

        for legacy_record in reversed(legacy_records):
            try:
                clean = validate_record_payload(legacy_record)
                date_value = str(legacy_record.get("date", "")).strip() or utc_now()

                connection.execute(
                    """
                    INSERT INTO production_records (
                        date,
                        product_name,
                        quantity,
                        good_quantity,
                        defect_quantity,
                        defect_reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        date_value,
                        clean["productName"],
                        clean["quantity"],
                        clean["goodQuantity"],
                        clean["defectQuantity"],
                        clean["defectReason"],
                    ),
                )
                migrated_count += 1
            except (ValueError, sqlite3.DatabaseError) as error:
                skipped_count += 1
                print(f"[MIGRATION] Запись пропущена: {error}")

        set_metadata(
            connection,
            MIGRATION_KEY,
            (
                f"completed:{utc_now()}:"
                f"migrated={migrated_count}:skipped={skipped_count}"
            ),
        )

        print(
            "[MIGRATION] JSON → SQLite: "
            f"перенесено {migrated_count}, пропущено {skipped_count}."
        )


def parse_record_id(path):
    prefix = "/api/records/"

    if not path.startswith(prefix):
        return None

    raw_id = path[len(prefix):]

    if not raw_id or "/" in raw_id:
        return None

    try:
        record_id = int(raw_id)
    except ValueError:
        return None

    return record_id if record_id > 0 else None


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
        parsed = urlparse(self.path)

        if parsed.path == "/api/records":
            self.handle_get_records(parse_qs(parsed.query))
            return

        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/records":
            self.handle_create_record()
            return

        self.send_json(404, {"error": "API-адрес не найден."})

    def do_PUT(self):
        path = urlparse(self.path).path
        record_id = parse_record_id(path)

        if record_id is None:
            self.send_json(404, {"error": "Запись не найдена."})
            return

        self.handle_update_record(record_id)

    def do_DELETE(self):
        path = urlparse(self.path).path
        record_id = parse_record_id(path)

        if record_id is None:
            self.send_json(404, {"error": "Запись не найдена."})
            return

        self.handle_delete_record(record_id)

    def handle_get_records(self, query):
        try:
            filters = parse_filters(query)
            self.send_json(200, get_records(filters))
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.DatabaseError as error:
            self.send_json(
                500,
                {"error": f"Не удалось прочитать базу данных: {error}"},
            )

    def handle_create_record(self):
        try:
            payload = self.read_json_body()
            record = create_record(payload)
            self.send_json(201, {"record": record})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Некорректный JSON."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.DatabaseError as error:
            self.send_json(
                500,
                {"error": f"Не удалось сохранить запись в базе: {error}"},
            )

    def handle_update_record(self, record_id):
        try:
            payload = self.read_json_body()
            record = update_record(record_id, payload)
            self.send_json(200, {"record": record})
        except RecordNotFoundError as error:
            self.send_json(404, {"error": str(error)})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Некорректный JSON."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.DatabaseError as error:
            self.send_json(
                500,
                {"error": f"Не удалось изменить запись: {error}"},
            )

    def handle_delete_record(self, record_id):
        try:
            delete_record(record_id)
            self.send_json(
                200,
                {"deleted": True, "id": record_id},
            )
        except RecordNotFoundError as error:
            self.send_json(404, {"error": str(error)})
        except sqlite3.DatabaseError as error:
            self.send_json(
                500,
                {"error": f"Не удалось удалить запись: {error}"},
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
    initialize_database()

    server = ThreadingHTTPServer((HOST, PORT), ProductionHandler)
    server.daemon_threads = True

    print("Сервер запущен:")
    print(f"http://localhost:{PORT}")
    print(f"База данных: {DB_FILE}")
    print("Для остановки нажмите Ctrl+C")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
