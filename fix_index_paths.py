import json
import os
import shutil
from typing import Any


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "data")
INDEX_FIELDS = ("archivo_maestro", "normas_json", "grafo_asociacion")


def resolve_data_dir(raw_data_dir: str | None) -> str:
    if not raw_data_dir:
        return DEFAULT_DATA_DIR
    if os.path.isabs(raw_data_dir):
        return raw_data_dir
    return os.path.abspath(os.path.join(BASE_DIR, raw_data_dir))


def load_data_dir() -> str:
    config: dict[str, Any] = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    return resolve_data_dir(os.getenv("DATA_DIR", config.get("data_dir")))


def normalize_relative_path(value: str) -> str:
    return value.replace("\\", "/")


def main() -> int:
    data_dir = load_data_dir()
    graph_dir = os.path.join(data_dir, "grafos")
    index_path = os.path.join(graph_dir, "diccionarios_index.json")

    if not os.path.exists(index_path):
        print(f"No se encontró el índice: {index_path}")
        return 1

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    changes = 0
    for entry in index:
        for field in INDEX_FIELDS:
            value = entry.get(field)
            if isinstance(value, str):
                normalized = normalize_relative_path(value)
                if normalized != value:
                    entry[field] = normalized
                    changes += 1

    if changes == 0:
        print(f"Sin cambios: {index_path}")
        return 0

    backup_path = index_path + ".bak"
    shutil.copy2(index_path, backup_path)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Actualizado: {index_path}")
    print(f"Respaldo: {backup_path}")
    print(f"Campos corregidos: {changes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
