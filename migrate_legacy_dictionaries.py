#!/usr/bin/env python3
"""Convert pre-2026 flat Diccionario data into the current project layout.

The conversion is idempotent and preserves the original top-level JSON and
GraphML files.  It creates the per-dictionary files expected by the current
application and replaces the index atomically after creating a backup.
"""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

import networkx as nx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    graph_dir = Path(args.data_dir).resolve() / "grafos"
    index_path = graph_dir / "diccionarios_index.json"
    with index_path.open(encoding="utf-8") as index_file:
        index = json.load(index_file)

    converted = 0
    new_index = []
    for entry in index:
        if "archivo_maestro" in entry:
            new_index.append(entry)
            continue

        json_name = entry.get("archivo_json")
        graphml_name = entry.get("archivo_graphml")
        if not json_name or not graphml_name:
            raise ValueError(f"Entrada legacy incompleta: {entry.get('nombre')!r}")

        legacy_json = graph_dir / json_name
        legacy_graphml = graph_dir / graphml_name
        if not legacy_json.is_file() or not legacy_graphml.is_file():
            raise FileNotFoundError(f"Faltan archivos para {entry.get('nombre')!r}")

        with legacy_json.open(encoding="utf-8") as dictionary_file:
            dictionary = json.load(dictionary_file)

        project_name = Path(json_name).stem
        project_dir = graph_dir / project_name
        project_dir.mkdir(exist_ok=True)
        master_name = f"{project_name}.json"
        shutil.copy2(legacy_json, project_dir / master_name)

        graph = nx.read_graphml(legacy_graphml)
        nx.write_gexf(graph, project_dir / "grafo_asociacion.gexf")
        normas_path = project_dir / "normas_asociacion.json"
        if not normas_path.exists():
            normas_path.write_text("{}\n", encoding="utf-8")

        new_index.append(
            {
                "nombre": entry["nombre"],
                "owner": entry.get("owner", "Migrado de GECO IINGEN"),
                "archivo_maestro": f"{project_name}/{master_name}",
                "normas_json": f"{project_name}/normas_asociacion.json",
                "grafo_asociacion": f"{project_name}/grafo_asociacion.gexf",
                "n_nodos": graph.number_of_nodes(),
                "n_tripletas": len(dictionary.get("edges", [])),
            }
        )
        converted += 1

    if not converted:
        print("No hay entradas legacy por convertir.")
        return 0

    backup_path = index_path.with_suffix(index_path.suffix + ".legacy-backup")
    if not backup_path.exists():
        shutil.copy2(index_path, backup_path)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=graph_dir, delete=False) as temp_file:
        json.dump(new_index, temp_file, ensure_ascii=False, indent=2)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)
    os.replace(temp_path, index_path)
    print(f"Convertidas {converted} entradas legacy; respaldo: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
