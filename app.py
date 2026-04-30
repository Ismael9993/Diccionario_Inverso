from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import json
import secrets
import networkx as nx
import threading
from collections import Counter
from Dic_Inv import (
    CONFIG,
    TextProcessor,
    GraphBuilder,
    ReverseDict,
    GRAPH_DIR,
    cargar_diccionario,
    get_client,
    listar_corpus,
    listar_documentos,
    descargar_documento,
    filtrar_documentos_por_metadatos_api,
    filtrar_documentos_por_varios_metadatos_api,
    obtener_metadatos_corpus,
    borrar_diccionario,
    ejecutar_pipeline_completo,
    finalizar_y_registrar_diccionario
)



from Dic_Inv import nlp 

# Si el error persiste, añade esta validación manual justo después de las importaciones:
try:
    if 'nlp' not in globals():
        import spacy
        print("Cargando modelo nlp en app.py...")
        nlp = spacy.load("es_core_news_lg")
except Exception as e:
    print(f"Error crítico cargando nlp: {e}")


# Lista global de diccionarios que NO se pueden borrar
DICCIONARIOS_PROTEGIDOS = [
    "02_Diccionario de Educación Sexual",
    "01_Diccionario_de_Medicina",
    "02_Diccionario_de_Educación_Sexual",
    "02_Diccionario_de_Identidades_y_Géneros",
    "02_Diccionario_de_ETS",
    "02_Diccionario_de_Parafilias",
    "02_Diccionario_de_General_de_Sexualidades",
    "02_Diccionario_de_Sexualidad_CDs",
    "03_Diccionario_de_Ingeniería_CDs",
    "03_Diccionario_de_Ingeniería_Química",
    "03_Diccionario_de_Ingeniería_Aeroespacial",
    "03_Diccionario de Ingeniería Aeronáutica",
    "03_Diccionario_de_Ingeniería_Mecatrónica",
    "03_Diccionario_de_Ingeniería_Electrónica",
    "03_Diccionario_de_Ingeniería_en_Sistemas_Computacionales",
    "03_Diccionario_de_Ingeniería_Mécanica_Automotriz"
]

url_prefix = CONFIG.get('url_prefix', '')

if url_prefix:
    static_url_path = '/' + url_prefix + '/static'
else:
    static_url_path = '/static'

app = Flask(__name__, static_folder="static", static_url_path=static_url_path, template_folder="templates")
if url_prefix:
    app.config['APPLICATION_ROOT'] = '/' + url_prefix

    # Middleware to set SCRIPT_NAME for proper url_for() generation behind proxy
    class PrefixMiddleware:
        def __init__(self, app, prefix):
            self.app = app
            self.prefix = prefix

        def __call__(self, environ, start_response):
            environ['SCRIPT_NAME'] = '/' + self.prefix
            return self.app(environ, start_response)

    app.wsgi_app = PrefixMiddleware(app.wsgi_app, url_prefix)

# Session configuration for GECO SSO authentication
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_PATH'] = '/'  # Avoid path issues behind reverse proxy
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes


# ============================================
# AUTHENTICATION HELPER
# ============================================

def _get_session_token():
    """Get the user token from session, if available."""
    if 'geco3user' in session and session['geco3user']:
        return session['geco3user'].get('token')
    return None


def _get_client():
    """
    Factory function to create an authenticated GECO3 client.
    Uses session token if available, otherwise falls back to anonymous.
    """
    token = _get_session_token()
    return get_client(token=token, is_encrypted=True)


# ============================================
# AUTHENTICATION ENDPOINTS
# ============================================

@app.route("/auth")
def auth():
    """
    Receive authentication redirect from GECO.
    GECO redirects here with query parameters:
    - token: User's session token (XOR encrypted, Base64 encoded)
    - name: User's display name
    - corpus: (Optional) Pre-selected corpus ID
    """
    token = request.args.get('token')
    name = request.args.get('name')
    corpus = request.args.get('corpus')

    # Handle space encoding in URL parameters
    if token:
        token = token.replace(" ", "+")

    session['geco3user'] = {
        'token': token,
        'name': name,
        'corpus': corpus
    }
    session.permanent = True

    # If corpus is provided, redirect to it; otherwise go to index
    if corpus:
        return redirect(url_for('index') + f'?corpus={corpus}')

    return redirect(url_for('index'))


@app.route("/logout")
def logout():
    """Clear GECO session and redirect to index."""
    session.pop('geco3user', None)
    return redirect(url_for('index'))


@app.route("/api/auth/status")
def auth_status():
    """Return current authentication status."""
    if 'geco3user' in session and session['geco3user']:
        user = session['geco3user']
        return jsonify({
            "ok": True,
            "authenticated": True,
            "name": user.get('name'),
            "corpus": user.get('corpus')
        })
    return jsonify({
        "ok": True,
        "authenticated": False,
        "name": None,
        "corpus": None
    })

state = {
    "status": "idle",
    "message": "",
    "current_graph": None,
    "builder": None,
    "processor": None,
    "reverse_dict": None,
    "last_graph_file": None,
    "current_diccionario": None,
    "base_de_datos": None,
}


def graph_to_json(G, top_n_nodes=None, terminos_validos=None):
    nodes = []
    edges = []
    
    if terminos_validos is not None and len(terminos_validos) > 0:
        nodes_list = [n for n in G.nodes() if str(n) in terminos_validos]
    else:
        nodes_list = list(G.nodes())

    if top_n_nodes:
        try:
            nodes_sorted = sorted(
                [(n, G.nodes[n]) for n in nodes_list],
                key=lambda x: x[1].get("frequency", 0),
                reverse=True,
            )[:top_n_nodes]
            nodes_list = [n for n, _ in nodes_sorted]
        except Exception:
            pass

    for n in nodes_list:
        data = G.nodes[n]
        nodes.append(
            {
                "id": n,
                "frequency": int(data.get("frequency", 0)),
                "degree": int(data.get("degree", G.degree(n))),
            }
        )

    for u, v, d in G.edges(data=True):
        if u in nodes_list and v in nodes_list:
            edges.append(
                {"source": u, "target": v,
                    "weight": float(d.get("weight", 1.0))}
            )

    return {"nodes": nodes, "edges": edges}


@app.route("/")
def index():
    # Reiniciar estado global para evitar carga automática accidental
    state["current_graph"] = None
    state["current_diccionario"] = None
    state["reverse_dict"] = None
    return render_template("index.html")


@app.route("/api/corpora", methods=["GET"])
def api_corpora():
    try:
        client = _get_client()
        # Include private corpora if user is authenticated
        include_private = _get_session_token() is not None
        corpus_list = listar_corpus(client, include_private=include_private)

        simplified = [
            {"id": c["id"], "nombre": c.get("nombre", c.get("titulo", ""))}
            for c in corpus_list
        ]

        # If user logged in with a specific corpus, filter to only that corpus
        session_corpus = None
        if 'geco3user' in session and session['geco3user']:
            session_corpus = session['geco3user'].get('corpus')

        if session_corpus:
            try:
                session_corpus_id = int(session_corpus)
                simplified = [c for c in simplified if c["id"] == session_corpus_id]
            except (ValueError, TypeError):
                pass

        return jsonify({"ok": True, "data": simplified})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# API: listar documentos de un corpus (ahora con filtrado opcional por metadatos)
@app.route("/api/documentos/<int:corpus_id>", methods=["GET"])
def api_documentos(corpus_id):
    """
    Obtiene documentos de un corpus, con opción de filtrar por uno o varios metadatos.
    - Sin filtros: /api/documentos/131
    - Filtro simple: /api/documentos/131?meta=Área&valor=Medicina
    - Múltiples filtros: /api/documentos/131?meta=Área,Lengua&valor=Medicina,Español
    """
    try:
        client = _get_client()
        meta_param = request.args.get("meta")
        valor_param = request.args.get("valor")

        # Caso: filtros separados por coma
        if meta_param and valor_param:
            metas = [m.strip() for m in meta_param.split(",")]
            valores = [v.strip() for v in valor_param.split(",")]

            if len(metas) > 1:
                documentos = filtrar_documentos_por_varios_metadatos_api(
                    client, corpus_id, metas, valores
                )
            else:
                documentos = filtrar_documentos_por_metadatos_api(
                    client, corpus_id, metas[0], valores[0]
                )

            simplified = [{"id": d["id"], "archivo": d["archivo"]} for d in documentos]
            return jsonify({"ok": True, "data": simplified, "filtered": True})

        # Si no se enviaron parámetros, listamos todos los documentos
        documentos = listar_documentos(client, corpus_id)
        simplified = [
            {"id": d["id"], "archivo": d.get("archivo", str(d.get("id")))}
            for d in documentos
        ]
        return jsonify({"ok": True, "data": simplified, "filtered": False})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# API: obtener metadatos y sus valores posibles de un corpus
@app.route("/api/metadatos/<int:corpus_id>", methods=["GET"])
def api_metadatos(corpus_id):
    """
    Devuelve los metadatos y sus valores posibles.
    Ejemplo de respuesta:
    {
      "ok": true,
      "data": [
        {"nombre": "Área", "valores": ["Medicina", "Ingeniería", "COVID"]}
      ]
    }
    """
    try:
        client = _get_client()
        metadatos = obtener_metadatos_corpus(client, corpus_id)
        resultado = [{"nombre": meta, "valores": valores} for meta, valores in metadatos.items()]
        return jsonify({"ok": True, "data": resultado})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json()
    corpus_id = data.get('corpus_id')
    doc_ids = data.get('doc_ids')
    dic_name = data.get('dic_name')

    if not corpus_id or not doc_ids or not dic_name:
        return jsonify({"ok": False, "error": "Faltan corpus_id, doc_ids o dic_name"}), 400

    # Reiniciar el estado para el nuevo proceso
    state["status"] = "processing"
    state["message"] = "Iniciando pipeline..."

    # Definimos el callback que Dic_Inv usará para avisarnos de cambios
    def mi_callback(nuevo_mensaje):
        state["message"] = nuevo_mensaje
        print(f"DEBUG PROGRESS: {nuevo_mensaje}")

    def run_pipeline():
        try:
            client = get_client()
            # PASAMOS mi_callback al argumento status_callback
            exito, msg = ejecutar_pipeline_completo(
                nombre_dic=dic_name,
                corpus_id=corpus_id,
                doc_ids=doc_ids,
                client=client,
                nlp_model=nlp,
                status_callback=mi_callback  # <--- ESTO ES LO QUE CONECTA TODO
            )
            if exito:
                state["status"] = "done"
                state["message"] = msg
            else:
                state["status"] = "error"
                state["message"] = msg
        except Exception as e:
            state["status"] = "error"
            state["message"] = str(e)

    thread = threading.Thread(target=run_pipeline)
    thread.start()

    return jsonify({"ok": True, "message": "Proceso iniciado en segundo plano"})

@app.route("/api/status", methods=["GET"])
def api_status():
    """Retorna el estado actual del procesamiento en segundo plano."""
    return jsonify({
        "status": state.get("status", "idle"),
        "message": state.get("message", "")
    })

# Listar diccionarios disponibles
@app.route("/api/diccionarios", methods=["GET"])
def api_diccionarios():
    index_path = os.path.join(GRAPH_DIR, "diccionarios_index.json")
    if not os.path.exists(index_path):
        return jsonify({"ok": True, "data": []})
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify({"ok": True, "data": data})


# Seleccionar y cargar un diccionario existente
@app.route("/api/load_diccionario", methods=["POST"])
def api_load_diccionario():
    data = request.get_json()
    nombre = data.get("nombre")
    if not nombre:
        return jsonify({"ok": False, "error": "Falta el nombre del diccionario."}), 400

    # Intentar carga normal
    grafo, base_de_datos, processor, builder = cargar_diccionario(nombre, nlp)
    
    # Si falla, intentar con guiones bajos (robustez ante espacios)
    if grafo is None:
        nombre_alt = nombre.replace(" ", "_")
        if nombre_alt != nombre:
            print(f"Reintentando carga con nombre normalizado: {nombre_alt}")
            grafo, base_de_datos, processor, builder = cargar_diccionario(nombre_alt, nlp)
            if grafo:
                nombre = nombre_alt # Usar el nombre que funcionó en el servidor

    if grafo is None:
        return jsonify({"ok": False, "error": "No se pudo cargar el diccionario."}), 404

    reverse_dict = ReverseDict(nombre, nlp)
    state.update(
        {
            "current_graph": grafo,
            "builder": builder,
            "processor": processor,
            "reverse_dict": reverse_dict,
            "current_diccionario": nombre,
            "base_de_datos": base_de_datos,
        }
    )

    # Ruta al archivo de normas del diccionario actual
    dic_dir = os.path.join(GRAPH_DIR, nombre)
    normas_path = os.path.join(dic_dir, "normas_maestras.json")
    terminos_validos = set()
    if os.path.exists(normas_path):
        with open(normas_path, "r", encoding="utf-8") as f:
            normas_data = json.load(f)
            # Las llaves ya vienen normalizadas (ej: "tumor_filoides")
            terminos_validos = set(normas_data.keys())

    return jsonify(
        {
            "ok": True,
            "message": f"Diccionario '{nombre}' cargado correctamente.",
            "graph": graph_to_json(grafo, top_n_nodes=1000, terminos_validos=terminos_validos),
        }
    )


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json()
    definition = data.get("definition", "")
    dic_name = data.get("diccionario")
    top_k = int(data.get("top_k", 20))

    if not definition:
        return jsonify({"ok": False, "error": "Falta la definición."}), 400

    if dic_name:
        # NORMALIZACIÓN CRÍTICA: Reemplazar espacios por guiones bajos
        dic_name = dic_name.replace(" ", "_")
        
        grafo, base_de_datos, processor, builder = cargar_diccionario(dic_name, nlp)
        if not grafo:
            return jsonify({"ok": False, "error": f"Diccionario '{dic_name}' no encontrado."}), 404
        rd = ReverseDict(dic_name, nlp)
    else:
        rd = state.get("reverse_dict")
        if rd is None:
            return jsonify({"ok": False, "error": "No hay diccionario cargado."}), 400

    resultados = rd.buscar(definition, n_sugerencias=top_k)
    if resultados and len(resultados) > 0:
        resultados_s = [{"palabra": str(r[0] if isinstance(r, tuple) else r)} for r in resultados]
    else:
        resultados_s = []
        
    return jsonify({"ok": True, "results": resultados_s})

@app.route("/api/node_info", methods=["POST"])
def api_node_info():
    data = request.get_json()
    node_id = data.get("node_id")
    dic_name = data.get("diccionario")

    if not node_id:
        return jsonify({"ok": False, "error": "Falta node_id."}), 400

    node_id_norm = node_id.lower().replace("_", " ") # Normalizar ID del grafo

    if state.get("current_diccionario") != dic_name and dic_name:
        # Normalizar para encontrar la base de datos correcta
        dic_name = dic_name.replace(" ", "_")
        
        grafo, base_de_datos, processor, builder = cargar_diccionario(dic_name, nlp)
        if base_de_datos is not None:
            state["base_de_datos"] = base_de_datos
            state["current_diccionario"] = dic_name
    
    base_de_datos = state.get("base_de_datos", [])
    
    definicion = "Definición no disponible en la base de datos."
    if base_de_datos:
        for row in base_de_datos:
            # Extraemos el término de 'Source' y la definición de 'Target'
            term_en_db = str(row.get('Source', '')).lower().replace("_", " ")

            if node_id_norm == term_en_db:
                definicion = row.get('Target', definicion)
                break

    return jsonify({"ok": True, "definicion": definicion})

@app.route("/api/delete_diccionario", methods=["POST"])
def api_delete_diccionario():
    data = request.get_json()
    nombre_dic = data.get('nombre')
    
    if not nombre_dic:
        return jsonify({"ok": False, "error": "Nombre requerido"}), 400

    # Bloqueo de seguridad para muestras (comprobamos nombre original y normalizado)
    if nombre_dic in DICCIONARIOS_PROTEGIDOS or nombre_dic.replace(" ", "_") in DICCIONARIOS_PROTEGIDOS:
        return jsonify({"ok": False, "error": "Este es un diccionario de muestra protegido y no puede eliminarse."}), 403
    
    # --- PASO CRUCIAL: Liberar memoria antes de borrar ---
    if state.get("current_diccionario") == nombre_dic:
        state["reverse_dict"] = None  # Liberamos el objeto que lee los archivos
        state["current_graph"] = None
        state["current_diccionario"] = None
    
    # Sugerencia: Un pequeño delay o recolección de basura manual ayuda en Windows
    import gc
    gc.collect() 

    usuario_actual = "Anónimo"
    if 'geco3user' in session and session['geco3user']:
        usuario_actual = session['geco3user'].get('name', 'Anónimo')

    exito, mensaje = borrar_diccionario(nombre_dic, usuario_actual)
    
    if exito:
        return jsonify({"ok": True, "message": mensaje})
    else:
        # El error 403 que viste es porque 'exito' fue False
        return jsonify({"ok": False, "error": mensaje}), 403

@app.route("/api/descargar/<nombre_dic>/<archivo>", methods=["GET"])
def api_descargar(nombre_dic, archivo):
    index_path = os.path.join(GRAPH_DIR, "diccionarios_index.json")
    if not os.path.exists(index_path):
        return jsonify({"ok": False, "error": "No hay diccionarios."}), 404
        
    with open(index_path, "r", encoding="utf-8") as f:
        diccionarios = json.load(f)
        
    dic_info = next((d for d in diccionarios if d["nombre"] == nombre_dic), None)
    if not dic_info:
        return jsonify({"ok": False, "error": "Diccionario no encontrado."}), 404
        
    owner = dic_info.get("owner", "Anónimo")
    usuario_actual = "Anónimo"
    
    if 'geco3user' in session and session['geco3user']:
        usuario_actual = session['geco3user'].get('name', 'Anónimo')
        
    permitido = False
    if owner == "Anónimo" and usuario_actual == "Anónimo":
        permitido = True
    elif owner == usuario_actual:
        permitido = True
        
    if not permitido:
        return jsonify({"ok": False, "error": "Acceso denegado. No eres el propietario de este diccionario."}), 403
        
    dic_dir = os.path.join(GRAPH_DIR, nombre_dic)
    if not os.path.exists(dic_dir) or not os.path.exists(os.path.join(dic_dir, archivo)):
        return jsonify({"ok": False, "error": "Archivo no encontrado en el servidor."}), 404
        
    return send_from_directory(dic_dir, archivo, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
