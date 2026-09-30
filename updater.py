from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "update_config.json"
VERSION_FILE = ROOT / "version.txt"
BACKUP_ROOT = ROOT / "update_backups"

PROTECTED_PREFIXES = (
    "data/",
    "server_data/",
    "update_backups/",
)

PROTECTED_FILES = {
    "update_config.json",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def current_version():
    if not VERSION_FILE.exists():
        return "0.0.0"
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def version_tuple(version):
    parts = []
    for part in version.strip().split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or 0))

    while len(parts) < 3:
        parts.append(0)

    return tuple(parts[:3])


def normalize_path(relative_path):
    return relative_path.replace("\\", "/").lstrip("/")


def is_protected(relative_path):
    normalized = normalize_path(relative_path)

    if normalized in PROTECTED_FILES:
        return True

    return any(normalized.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def github_raw_base(config):
    owner = config["repo_owner"].strip()
    repo = config["repo_name"].strip()
    branch = config.get("branch", "main").strip()
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/"


def download_bytes(url):
    request = Request(
        url,
        headers={"User-Agent": "production-system-updater/1.1"},
    )

    with urlopen(request, timeout=15) as response:
        return response.read()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def file_is_current(path, expected_hash):
    if not path.exists() or not expected_hash:
        return False

    return sha256_file(path).lower() == expected_hash.lower()


def backup_file(path, relative_path, backup_dir):
    if not path.exists():
        return

    destination = backup_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def atomic_replace(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_target = target.with_name(target.name + ".update_tmp")
    shutil.copy2(source, temporary_target)
    os.replace(temporary_target, target)


def main():
    print("=" * 56)
    print("   Мини-система учёта производства — обновление")
    print("=" * 56)

    if not CONFIG_FILE.exists():
        print("Ошибка: отсутствует update_config.json")
        return

    config = read_json(CONFIG_FILE)
    base_url = github_raw_base(config)

    local_version = current_version()
    manifest_url = base_url + config.get("manifest_file", "manifest.json")

    print(f"Текущая версия: {local_version}")
    print("Проверяю обновления...")

    try:
        manifest_data = download_bytes(manifest_url)
        manifest = json.loads(manifest_data.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        print(f"Не удалось проверить обновление: {error}")
        return

    remote_version = str(manifest.get("version", "0.0.0"))
    print(f"Версия на сервере: {remote_version}")

    if version_tuple(remote_version) <= version_tuple(local_version):
        print("Обновление не требуется.")
        return

    files = manifest.get("files", [])
    if not files:
        print("В manifest.json нет файлов для обновления.")
        return

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = BACKUP_ROOT / timestamp
    temp_dir = Path(tempfile.mkdtemp(prefix="production_update_"))
    downloaded = []

    try:
        print()
        print("Проверяю файлы:")

        for item in files:
            relative_path = normalize_path(item["path"])
            expected_hash = item.get("sha256", "")
            target = ROOT / relative_path

            if is_protected(relative_path):
                print(f"  ЗАЩИЩЁН   {relative_path}")
                continue

            if file_is_current(target, expected_hash):
                print(f"  БЕЗ ИЗМЕНЕНИЙ  {relative_path}")
                continue

            data = download_bytes(base_url + relative_path)

            if expected_hash:
                actual_hash = sha256_bytes(data)
                if actual_hash.lower() != expected_hash.lower():
                    raise ValueError(
                        f"Контрольная сумма не совпала: {relative_path}"
                    )

            temp_path = temp_dir / relative_path
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_bytes(data)
            downloaded.append((relative_path, temp_path))
            print(f"  СКАЧАН    {relative_path}")

        if not downloaded:
            VERSION_FILE.write_text(remote_version + "\n", encoding="utf-8")
            print()
            print(f"Файлы уже актуальны. Версия: {remote_version}")
            return

        print()
        print("Применяю обновление:")

        for relative_path, temp_path in downloaded:
            target = ROOT / relative_path
            backup_file(target, relative_path, backup_dir)
            atomic_replace(temp_path, target)
            print(f"  ОБНОВЛЁН  {relative_path}")

        VERSION_FILE.write_text(remote_version + "\n", encoding="utf-8")

        print()
        print(f"Готово. Версия обновлена до {remote_version}")
        print(f"Резервная копия: {backup_dir}")

    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        print()
        print(f"Обновление остановлено: {error}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
