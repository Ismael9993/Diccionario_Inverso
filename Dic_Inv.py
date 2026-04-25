import os
import re
import pandas as pd
import requests
import spacy
import io
from tqdm import tqdm
import nltk
import re
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import json
from typing import List, Dict, Any, Optional
import networkx as nx
from collections import defaultdict, Counter
from operator import itemgetter
from text2graphapi.src.Cooccurrence import Cooccurrence
from geco3_client.client import GECO3Client


# --- 1. CONFIGURACIÓN BASE DE RUTAS ---
BASE_DIR = os.getcwd()

# Directorio principal de datos (Excel de entrada, etc.)
DATA_DIR = os.path.join(BASE_DIR, "data")

# Directorio maestro de diccionarios (Aquí vivirán las carpetas de cada proyecto)
GRAPH_DIR = os.path.join(DATA_DIR, "grafos")

# Aseguramos que existan las carpetas base
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(GRAPH_DIR, exist_ok=True)



# --------------------------------------------
# Configuración geco3_client
# --------------------------------------------




# CONFIGURACIÓN BASE (desde variables de entorno o config.json)
def load_config() -> Dict[str, Any]:
    """
    Carga configuración desde variables de entorno o archivo config.json
    Orden de prioridad: Variables de entorno > config.json > valores por defecto
    """
    config: Dict[str, Any] = {}

    # Intentar cargar desde archivo config.json
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"Advertencia: No se pudo cargar config.json: {e}")

    # Variables de entorno tienen prioridad
    config["base_url"] = os.getenv("GECO_BASE_URL", config.get("base_url", "http://www.geco.unam.mx/geco3/"))
    config["anon_user"] = os.getenv("GECO_ANON_USER", config.get("anon_user", None))
    config["anon_pass"] = os.getenv("GECO_ANON_PASS", config.get("anon_pass", None))
    config["app_name"] = os.getenv("GECO_APP_NAME", config.get("app_name", None))
    config["app_password"] = os.getenv("GECO_APP_PASSWORD", config.get("app_password", None))
    config["user_token"] = os.getenv("GECO_USER_TOKEN", config.get("user_token", None))
    config["data_dir"] = os.getenv("DATA_DIR", DATA_DIR)
    return config

# Cargar configuración
CONFIG = load_config()


def get_client(token=None, is_encrypted=True):
    """
    Factory function to create an authenticated GECO3 client.

    Args:
        token: User token from GECO SSO (optional). If None, uses anonymous login.
        is_encrypted: Whether the token is XOR encrypted (default True for SSO tokens).

    Returns:
        Authenticated GECO3Client instance.
    """
    client = GECO3Client(
        host=CONFIG["base_url"],
        anon_user=CONFIG["anon_user"],
        anon_pass=CONFIG["anon_pass"],
        app_name=CONFIG["app_name"],
        app_password=CONFIG["app_password"]
    )

    try:
        client.login(token=token, is_token_encrypted=is_encrypted if token else False)
    except Exception as e:
        print(f"Token login failed, falling back to anonymous: {e}")
        client.login()  # Fallback to anonymous

    return client



# ---------------------------
# INICIALIZACIÓN DE MODELOS
# ---------------------------

import spacy
import sys
import subprocess

def asegurar_modelo_spacy(nombre_modelo="es_core_news_lg"):
    """Verifica si el modelo de spaCy está instalado, si no, lo descarga."""
    if not spacy.util.is_package(nombre_modelo):
        print(f"Instalando modelo {nombre_modelo} automáticamente...")
        subprocess.check_call([sys.executable, "-m", "spacy", "download", nombre_modelo])
    else:
        print(f"Modelo {nombre_modelo} detectado correctamente.")

# Llamar a la función antes de cargar el nlp
asegurar_modelo_spacy("es_core_news_lg")
try:
    nlp = spacy.load("es_core_news_lg")
except Exception as e:
    print(f"Error al cargar el modelo: {e}")

"""

# Stopwords ampliadas 
STOPWORDS = set(STOP_WORDS)
STOPWORDS.update([
    'ser', 'estar', 'haber', 'tener', 'hacer', 'poder', 'deber',
    'querer', 'ir', 'ver', 'dar', 'saber', 'decir', 'llegar',
    'pasar', 'poner', 'parecer', 'quedar', 'creer', 'llevar',
    'dejar', 'seguir', 'encontrar', 'llamar', 'venir', 'pensar',
    'salir', 'volver', 'tomar', 'conocer', 'vivir', 'sentir',
    'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete',
    'ocho', 'nueve', 'diez', 'cien', 'mil', 'primero', 'segundo',
    'último', 'mismo', 'otro', 'todo', 'cada', 'mucho', 'poco',
    'más', 'menos', 'muy', 'tan', 'tanto', 'bastante', 'demasiado'
])
"""



# ---------------------------------------------------------------
# --- FUNCIONES DE NAVEGACIÓN GECO3 --
# ---------------------------------------------------------------


# FUNCIONES DEL CORPUS (actualizadas con filtrado por metadatos)
def listar_corpus(client, include_private=False):
    """
    Lista los corpus disponibles desde la API usando GECO3Client.

    Args:
        client: Authenticated GECO3Client instance.
        include_private: If True, also fetches private/collaborative corpora.

    Returns:
        List of corpus dictionaries.
    """
    # Si hay app token, usar corpus de la app; si no, usar corpus públicos
    if client.is_app_logged():
        corpus_list = client.corpus_app()
    else:
        corpus_list = client.corpus_publicos()

    # Include private corpora if requested and user is authenticated
    if include_private:
        try:
            private_corpora = client.corpus_privados()
            existing_ids = {c["id"] for c in corpus_list}
            for c in private_corpora:
                if c["id"] not in existing_ids:
                    corpus_list.append(c)
        except Exception:
            pass  # Ignore if private corpora fetch fails

    print("\nCorpus disponibles:\n")
    for i, c in enumerate(corpus_list, 1):
        print(f"{i}. {c['nombre']} (ID: {c['id']})")
    return corpus_list


def elegir_corpus(corpus_list):
    """Permite elegir un corpus de la lista mostrada."""
    idx = int(input("\nElige un corpus: "))
    return corpus_list[idx - 1]


def elegir_corpus_multiple(corpus_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Permite elegir uno o varios corpus por número, separados por comas."""
    print(f"\n{len(corpus_list)} corpus disponibles.")
    indices_str: str = input("\nElige corpus (ej: 1,3) o presiona Enter para el primero: ").strip()
    if not indices_str:
        return [corpus_list[0]] if corpus_list else []
    
    try:
        indices_list: List[int] = [int(x.strip()) - 1 for x in indices_str.split(",") if x.strip().isdigit()]
        seleccionados: List[Dict[str, Any]] = [corpus_list[i] for i in indices_list if 0 <= i < len(corpus_list)]
        if not seleccionados:
            print("Selección inválida. Se procesará el primero.")
            return [corpus_list[0]] if corpus_list else []
        return seleccionados
    except Exception:
        print("Entrada no válida. Se procesará el primero.")
        return [corpus_list[0]] if corpus_list else []


def listar_documentos(client, corpus_id):
    """
    Lista documentos dentro de un corpus usando GECO3Client.

    Args:
        client: Authenticated GECO3Client instance.
        corpus_id: ID of the corpus.

    Returns:
        List of document dictionaries.
    """
    documentos = client.docs_corpus(corpus_id)
    print("\nDocumentos disponibles:\n")
    for i, d in enumerate(documentos, 1):
        print(f"{i}. {d['archivo']} (ID: {d['id']})")
    return documentos


def elegir_documentos(documentos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Permite seleccionar documentos por número."""
    print(f"\n{len(documentos)} documentos disponibles:\n")
    for i, d in enumerate(documentos, 1):
        print(f"{i}. {d.get('archivo', d.get('name', 'Desconocido'))} (ID: {d['id']})")
        
    indices_str: str = input("\nElige documentos (ej: 1,3,5) o presiona Enter para procesar todos: ").strip()
    if not indices_str:
        return documentos
        
    try:
        indices_list: List[int] = [int(x.strip()) - 1 for x in indices_str.split(",") if x.strip().isdigit()]
        seleccionados: List[Dict[str, Any]] = [documentos[i] for i in indices_list if 0 <= i < len(documentos)]
        if not seleccionados:
            print("Selección inválida. Se procesarán todos.")
            return documentos
        return seleccionados
    except Exception:
        print("Entrada no válida. Se procesarán todos.")
        return documentos


def descargar_documento(client, corpus_id, doc_id):
    """
    Descarga un documento específico por ID usando GECO3Client.

    Args:
        client: Authenticated GECO3Client instance.
        corpus_id: ID of the corpus.
        doc_id: ID of the document.

    Returns:
        Document content as string.
    """
    return client.doc_content(corpus_id, doc_id)



# NUEVA FUNCIÓN: FILTRAR POR METADATOS
def filtrar_documentos_por_metadatos(client: Any, corpus_id: str) -> List[Dict[str, Any]]:
    """
    Descarga los metadatos del corpus usando GECO3Client.docs_tabla()
    y permite filtrar y seleccionar documentos por múltiples valores de metadatos.

    Args:
        client: Authenticated GECO3Client instance.
        corpus_id: ID of the corpus.
    """
    try:
        # Obtener documentos con metadatos usando GECO3Client
        docs: List[Dict[str, Any]] = client.docs_tabla(corpus_id)
    except Exception as e:
        print(f"Error al obtener metadatos del corpus: {e}")
        return []

    if not docs:
        print("No hay documentos disponibles en este corpus.\n")
        return []
        
    opcion: str = input("\n¿Deseas filtrar los documentos por metadatos? (s/n): ").strip().lower()
    if opcion != "s":
        print("No se aplicará ningún filtro.\n")
        documentos_disponibles: List[Dict[str, Any]] = [{"id": doc["id"], "archivo": doc["name"]} for doc in docs]
        return elegir_documentos(documentos_disponibles)

    # Obtener todos los nombres de metadatos disponibles
    metadatos_disponibles: set[str] = set()
    for doc in docs:
        metadatos_disponibles.update(doc.get("metadata", {}).keys())

    if not metadatos_disponibles:
        print("No hay metadatos disponibles para este corpus.\n")
        documentos_disponibles = [{"id": doc["id"], "archivo": doc["name"]} for doc in docs]
        return elegir_documentos(documentos_disponibles)

    metadatos_lista: List[str] = sorted(list(metadatos_disponibles))
    
    documentos_finales: Dict[str, Dict[str, Any]] = {}  # dict para evitar duplicados por ID

    while True:
        # Mostrar metadatos disponibles
        print("\nMetadatos disponibles para filtrar:")
        for i, meta_nombre in enumerate(metadatos_lista, 1):
            print(f"{i}. {meta_nombre}")

        # Elegir metadato
        try:
            idx: int = int(input("\nSelecciona el número del metadato: ")) - 1
            if not (0 <= idx < len(metadatos_lista)):
                print("Selección inválida.")
                continue
            meta_nombre: str = metadatos_lista[idx]
        except ValueError:
            print("Entrada no válida.")
            continue

        # Obtener todos los valores disponibles para ese metadato
        valores_disponibles: set[Any] = set()
        for doc in docs:
            valor = doc.get("metadata", {}).get(meta_nombre)
            if valor is not None:
                valores_disponibles.add(valor)
        valores_lista: List[Any] = sorted(list(valores_disponibles))

        if not valores_lista:
            print(f"No hay valores registrados para el metadato '{meta_nombre}'.")
            continue

        print(f"\nValores disponibles para '{meta_nombre}':")
        for i, v in enumerate(valores_lista, 1):
            print(f"{i}. {v if v else '(vacío)'}")

        try:
            vidx: int = int(input(f"\nElige el número del valor para '{meta_nombre}': ")) - 1
            if not (0 <= vidx < len(valores_lista)):
                print("Selección inválida.")
                continue
            valor_elegido = valores_lista[vidx]
        except ValueError:
            print("Entrada no válida.")
            continue
            
        print(f"\nDocumentos donde '{meta_nombre}' = '{valor_elegido}':\n")

        # Filtrar los documentos
        documentos_filtrados: List[Dict[str, Any]] = []
        for doc in docs:
            if doc.get("metadata", {}).get(meta_nombre) == valor_elegido:
                documentos_filtrados.append({"id": doc["id"], "archivo": doc["name"]})

        if not documentos_filtrados:
            print("No se encontraron documentos con ese filtro.\n")
        else:
            # Seleccionar documentos de este filtro
            seleccionados = elegir_documentos(documentos_filtrados)
            for doc in seleccionados:
                documentos_finales[doc["id"]] = doc
            print(f"Se han añadido {len(seleccionados)} documentos a tu selección general.")
            
        otra_vez: str = input("\n¿Deseas seleccionar documentos usando otro metadato o valor? (s/n): ").strip().lower()
        if otra_vez != 's':
            break

    lista_final: List[Dict[str, Any]] = list(documentos_finales.values())
    if not lista_final:
        print("\nNo terminaste seleccionando ningún documento por metadatos.")
        return []
        
    # Mostrar resumen de lo seleccionado
    print(f"\n=== Resumen de Selección ===")
    print(f"Total de documentos únicos seleccionados: {len(lista_final)}")
    for i, d in enumerate(lista_final, 1):
        print(f"{i}. {d.get('archivo', 'Desconocido')} (ID: {d['id']})")
    
    return lista_final

def filtrar_documentos_por_metadatos_api(client, corpus_id, meta_nombre, valor):
    """
    Versión no interactiva para Flask.
    Devuelve lista de documentos que cumplen el filtro (sin pedir input()).
    Usa GECO3Client.docs_tabla() para obtener datos.

    Args:
        client: Authenticated GECO3Client instance.
        corpus_id: ID of the corpus.
        meta_nombre: Name of the metadata field to filter by.
        valor: Value to match.

    Returns:
        List of document dictionaries matching the filter.
    """
    try:
        # Obtener documentos con metadatos usando GECO3Client
        docs = client.docs_tabla(corpus_id)
    except Exception as e:
        print(f"Error al obtener documentos: {e}")
        return []

    # Filtrar documentos por metadato y valor
    documentos_filtrados = []
    for doc in docs:
        doc_valor = doc.get("metadata", {}).get(meta_nombre)
        if doc_valor and doc_valor.strip().lower() == valor.strip().lower():
            documentos_filtrados.append({"id": doc["id"], "archivo": doc["name"]})

    return documentos_filtrados


# NUEVA FUNCIÓN: FILTRAR POR VARIOS METADATOS (para API Flask/app.py)

def filtrar_documentos_por_varios_metadatos_api(client, corpus_id, metas, valores):
    """
    Filtra documentos que cumplan simultáneamente varios metadatos y valores.
    Ejemplo:
        metas = ["Área", "Lengua"]
        valores = ["Medicina", "Español"]
    Devuelve una lista de documentos (diccionarios con id y archivo).
    Usa GECO3Client.docs_tabla() para obtener datos.

    Args:
        client: Authenticated GECO3Client instance.
        corpus_id: ID of the corpus.
        metas: List of metadata field names.
        valores: List of values to match (parallel to metas).

    Returns:
        List of document dictionaries matching all filters.
    """
    try:
        # Obtener documentos con metadatos usando GECO3Client
        docs = client.docs_tabla(corpus_id)
    except Exception as e:
        print(f"Error al obtener documentos: {e}")
        return []

    # Crear lista de filtros (nombre_metadato, valor_esperado)
    filtros = list(zip(metas, valores))

    # Filtrar documentos que cumplan TODOS los criterios
    documentos_filtrados = []
    for doc in docs:
        metadata = doc.get("metadata", {})
        # Verificar que todos los pares (metadato, valor) coincidan
        cumple_todos = all(
            metadata.get(meta_nombre) == valor
            for meta_nombre, valor in filtros
        )
        if cumple_todos:
            documentos_filtrados.append({"id": doc["id"], "archivo": doc["name"]})

    return documentos_filtrados


def obtener_metadatos_corpus(client, corpus_id):
    """
    Obtiene los metadatos disponibles en un corpus y sus valores únicos.

    Args:
        client: Authenticated GECO3Client instance.
        corpus_id: ID of the corpus.

    Returns:
        Dictionary mapping metadata names to lists of unique values.
    """
    docs = client.docs_tabla(corpus_id)

    metadatos = {}
    for doc in docs:
        for key, value in doc.get("metadata", {}).items():
            if key not in metadatos:
                metadatos[key] = set()
            if value:
                metadatos[key].add(value)

    # Convert sets to sorted lists
    return {k: sorted(list(v)) for k, v in metadatos.items()}

# --------------------------------------------
#   Extractor de términos y definiciones (versión mejorada)
# --------------------------------------------

# Verbos que invierten roles: término a la DERECHA del verbo
VERBOS_INVERSOS: set = {"denominar", "conocer", "llamar", "designar", "apellidar"}
# Verbos cuya presencia indica una definición legítima
VERBOS_DEFINITORIOS: List[str] = ["ser", "definir", "conocer", "entender", "identificar", "denominar"]
# Núcleos nominales genéricos que no constituyen términos válidos
BLACKLIST_NUCLEOS: set = {
    "caso", "ejemplo", "vía", "manera", "forma", "tipo", "parte",
    "aspecto", "cosa", "hecho", "vez", "tiempo", "lugar", "situación",
    "resultado", "proceso", "problema", "año", "mes", "día", "síntoma", "transmisión",
}
# Palabras que indican perífrasis verbal (se ignoran como verbo principal)
VERBOS_MODALES: set = {"poder", "deber", "soler", "querer", "ir"}
# Verbos que invalidan una definición como verbo principal
VERBOS_PROHIBIDOS: set = {"haber", "existir", "tener", "parecer"}
PALABRAS_HAY: set = {"hay", "hubo", "había", "habrá", "existen"}
# Primeras palabras post-verbo que indican definición válida con 'ser'
KEYWORDS_DEFINITORIAS: set = {
    "entendido", "considerado", "definido", "visto", "la", "el", "un",
    "una", "aquello", "capacidad", "proceso", "enfermedad", "infección",
}
# Participios pasivos que invalidan el patrón con 'ser'
VERBOS_ACCION_PASIVA: set = {"aislado", "identificado", "creado", "modificado", "estudiado"}
# Adjetivos/determinantes que indican sujeto incompleto
PALABRAS_BASURA_INICIO: set = {
    "otro", "otra", "otros", "otras", "último", "últimos",
    "primer", "primero", "cada", "alguno", "nuevo", "nueva",
}


class TermExtractor:
    def __init__(self, nlp_model):
        self.nlp = nlp_model
        self.nlp.max_length = 1500000

    def limpiar_texto_avanzado(self, texto: str) -> str:
        """
        Limpia el texto preservando fronteras semánticas.

        MEJORA: Procesa línea a línea. Las líneas en MAYÚSCULAS cortas
        (títulos/índices) se marcan con [TITULO] para que el filtro de
        oraciones las descarte sin que spaCy las fusione con el contenido.
        """
        lineas = texto.splitlines()
        resultado: List[str] = []
        for linea in lineas:
            linea_strip = linea.strip()
            if not linea_strip:
                continue
            es_titulo = (
                len(linea_strip) < 65
                and linea_strip == linea_strip.upper()
                and not any(c in linea_strip for c in [".", ",", ";", "?", "!"])
            )
            resultado.append("[TITULO]." if es_titulo else linea_strip)
        texto_unido = " ".join(resultado)
        texto_unido = re.sub(r"https?://\S+", "", texto_unido)
        texto_unido = re.sub(r"\S+@\S+", "", texto_unido)
        texto_unido = re.sub(r"\b\d+\b", "", texto_unido)
        return re.sub(r"\s+", " ", texto_unido).strip()


    def _es_oracion_valida(self, sent: spacy.tokens.Span) -> bool:
        """Descarta oraciones que son títulos, índices o fragmentos sin verbo."""
        if "[TITULO]" in sent.text:
            return False
        tokens_validos = [t for t in sent if not t.is_punct and not t.is_space]
        if len(tokens_validos) < 5:
            return False
        if not any(t.pos_ in {"VERB", "AUX"} for t in tokens_validos):
            return False
        tokens_mayus = sum(1 for t in tokens_validos if t.text.isupper() and len(t.text) > 2)
        if tokens_mayus / len(tokens_validos) > 0.5:
            return False
        return True

    def _es_estructura_inversa(self, verbo: spacy.tokens.Token, sent: spacy.tokens.Span) -> bool:
        """Detecta construcción pasiva refleja 'se denomina/llama/conoce'.
        En estos casos el término está a la DERECHA del verbo."""
        if verbo.lemma_ not in VERBOS_INVERSOS:
            return False
        return any(t.text.lower() == "se" and t.i < verbo.i for t in sent)

    def _extraer_termino_post_verbo(self, verbo: spacy.tokens.Token, sent: spacy.tokens.Span) -> str:
        """Extrae el término candidato a la derecha del verbo (estructura inversa)."""
        doc = verbo.doc
        inicio = verbo.i + 1
        if inicio < sent.end and doc[inicio].lemma_ == "como":
            inicio += 1
        tokens: List[spacy.tokens.Token] = []
        for t in doc[inicio:sent.end]:
            if t.text in {".", ",", ";", ":"} or t.pos_ == "VERB":
                break
            tokens.append(t)
            if len(tokens) >= 5:
                break
        return "".join(t.text_with_ws for t in tokens).strip()

    def _validar_nucleo_nominal(self, doc_termino: spacy.tokens.Doc) -> bool:
        """Valida el término por su núcleo nominal (MEJORA CLAVE).
        Aplica BLACKLIST_NUCLEOS independientemente de la longitud del término."""
        sustantivos = [t for t in doc_termino if t.pos_ in {"NOUN", "PROPN"}]
        if not sustantivos:
            return False
        nucleo = sustantivos[-1]
        return nucleo.lemma_.lower() not in BLACKLIST_NUCLEOS

    def normalizar_termino(self, texto: str) -> str:
        """Normaliza el texto de un término candidato."""
        t = texto.lower().strip()
        t = re.sub(r'^[a-z0-9]{1,3}[\)\.]\s+', '', t)
        t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
        t = re.sub(r'[\[\]\(\)\{\}]', '', t)
        t = re.sub(r'[—–_•·]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        t = re.sub(r'^\w+mente\s+', '', t)
        # Deduplicación de palabras
        palabras = t.split()
        vistas: List[str] = []
        for p in palabras:
            if p not in vistas:
                vistas.append(p)
        t = " ".join(vistas)
        # Eliminar artículos/preposiciones al inicio/final
        patron_inicio = r'^(que|puesto que|puesto|el|la|los|las|un|una|unos|unas|de|del|y|o|en|con|para|por|a|pero|estas|esta|este)\s+'
        patron_final  = r'\s+(que|el|la|los|las|un|una|unos|unas|de|del|y|o|en|con|para|por|a|pero|estas|esta|este|se|no)$'
        for _ in range(3):
            t = re.sub(patron_inicio, '', t)
            t = re.sub(patron_final, '', t)
        t = re.sub(r'^[:,\.\-\s]+|[:,\.\-\s]+$', '', t)
        return t.strip().capitalize()



    def extraer_a_excel(
        self,
        contenidos: List[Dict[str, str]],
        nombre_archivo_salida: str,
        incluir_verbo: bool = False,
    ) -> None:
        """
        Extrae pares término-definición y los exporta a Excel.

        Args:
            contenidos: Lista de dicts con clave 'texto'.
            nombre_archivo_salida: Ruta del archivo .xlsx de salida.
            incluir_verbo: Si True, incluye columna 'Verbo' (por defecto False).
        """
        todas_las_tripletas: List[Dict[str, str]] = []

        for item in contenidos:
            texto_limpio = self.limpiar_texto_avanzado(item['texto'])
            chunks = [texto_limpio[i:i + 100_000] for i in range(0, len(texto_limpio), 100_000)]

            for chunk in chunks:
                doc = self.nlp(chunk)
                for sent in doc.sents:

                    # FILTRO 1: calidad mínima de la oración
                    if not self._es_oracion_valida(sent):
                        continue

                    # FILTRO 2: verbo definitorio
                    verbo = next((t for t in sent if t.lemma_ in VERBOS_DEFINITORIOS), None)
                    if not verbo:
                        continue
                    if verbo.lemma_ in VERBOS_PROHIBIDOS or verbo.text.lower() in PALABRAS_HAY:
                        continue
                    if verbo.i > sent.start:
                        if sent.doc[verbo.i - 1].lemma_ in VERBOS_MODALES:
                            continue
                    if verbo.dep_ == "aux" or (verbo.head.pos_ == "VERB" and verbo.head.i != verbo.i):
                        continue

                    # Validación adicional para 'ser'
                    if verbo.lemma_ == "ser":
                        post = [t for t in sent if t.i > verbo.i]
                        if not post:
                            continue
                        primera = post[0]
                        if primera.pos_ not in {"DET", "NOUN"} and primera.lemma_ not in KEYWORDS_DEFINITORIAS:
                            continue
                        if primera.lemma_ in VERBOS_ACCION_PASIVA:
                            continue

                    # EXTRACCIÓN con detección de estructura inversa
                    if self._es_estructura_inversa(verbo, sent):
                        termino_raw = self._extraer_termino_post_verbo(verbo, sent)
                        definicion_raw = "".join(t.text_with_ws for t in sent if t.i < verbo.i).strip()
                    else:
                        posibles = [t for t in sent if t.i < verbo.i]
                        if len(posibles) > 5:
                            posibles = posibles[-5:]
                        tokens_sujeto: List[spacy.tokens.Token] = []
                        encontro_sustantivo = False
                        for t in reversed(posibles):
                            if t.text.isupper() and len(t.text) > 3:
                                break
                            if t.pos_ in {"VERB", "AUX"}:
                                break
                            if t.text.lower() in {"que", "puesto", ",", ".", ";", ":", "¿", "¡"}:
                                break
                            if t.pos_ == "ADV" and t.i == verbo.i - 1:
                                break
                            if t.pos_ in {"NOUN", "PROPN"}:
                                encontro_sustantivo = True
                            tokens_sujeto.insert(0, t)
                        if not encontro_sustantivo:
                            continue
                        termino_raw = "".join(t.text_with_ws for t in tokens_sujeto)
                        definicion_raw = "".join(t.text_with_ws for t in sent if t.i > verbo.i).strip()

                    # NORMALIZACIÓN Y VALIDACIÓN DEL TÉRMINO
                    termino = self.normalizar_termino(termino_raw)
                    if not termino or len(termino.split()) > 5:
                        continue

                    doc_termino = self.nlp(termino)
                    if doc_termino and doc_termino[0].lemma_.lower() in PALABRAS_BASURA_INICIO:
                        continue
                    if any(t.lemma_ in {"haber", "ser", "estar", "hacer"} for t in doc_termino):
                        continue
                    if not self._validar_nucleo_nominal(doc_termino):
                        continue

                    # LIMPIEZA DE DEFINICIÓN
                    definicion = re.sub(r'^(como|es|son)\s+', '', definicion_raw, flags=re.IGNORECASE)
                    definicion = re.sub(r'^[:,\s]+', '', definicion).split(". ")[0]

                    # Umbral mejorado: longitud + sustantivo presente
                    doc_def = self.nlp(definicion)
                    tiene_sust = any(t.pos_ in {"NOUN", "PROPN"} for t in doc_def)
                    if len(definicion) < 30 or not tiene_sust:
                        continue

                    todas_las_tripletas.append({
                        'Término':      termino,
                        'Verbo':        verbo.lemma_.lower(),
                        'Definiciones': definicion.capitalize(),
                    })

        # GUARDADO
        if not todas_las_tripletas:
            print("No se encontraron términos para exportar.")
            return

        df = pd.DataFrame(todas_las_tripletas).drop_duplicates(subset=['Término'])
        columnas = ['Término', 'Verbo', 'Definiciones'] if incluir_verbo else ['Término', 'Definiciones']
        df[columnas].to_excel(nombre_archivo_salida, index=False)
        print(f"Excel generado con {len(df)} términos: '{nombre_archivo_salida}'")





# ---------------------------------------------------------------
# PROCESAMIENTO DE CORPUS (TextProcessor) (para API Flask/app.py)
# ---------------------------------------------------------------


class TextProcessor:
    def __init__(self, excel_filename, nombre_diccionario, client_geco=None, nlp_model=None):
        """
        Ahora recibe 'nombre_diccionario' para crear una ruta única.
        """
        self.nombre_dic = nombre_diccionario.replace(" ", "_")
        self.client_geco = client_geco
        
        # Ruta base del proyecto dentro de 'data/grafos/'
        # Esto coincide con la lógica de Funciones_Dicc.py
        self.project_dir = os.path.join(GRAPH_DIR, self.nombre_dic)
        
        # Subcarpetas específicas para este diccionario
        self.ruta_terminos = os.path.join(self.project_dir, 'terminos')
        self.ruta_lematizados = os.path.join(self.project_dir, 'terminos_lematizados')
        self.geco_limpio = os.path.join(self.project_dir, 'corpus_limpio')
        self.geco_lematizado = os.path.join(self.project_dir, 'corpus_lematizado')
        
        # Crear la estructura de carpetas automáticamente
        os.makedirs(self.ruta_terminos, exist_ok=True)
        os.makedirs(self.ruta_lematizados, exist_ok=True)
        os.makedirs(self.geco_limpio, exist_ok=True)
        os.makedirs(self.geco_lematizado, exist_ok=True)

        # Configuración de Excel y NLP
        #(más flexible):
        if excel_filename:
            # Si excel_filename ya es una ruta completa (absoluta), la usa. 
            # Si es solo un nombre, lo busca en DATA_DIR.
            self.excel_path = excel_filename if os.path.isabs(excel_filename) else os.path.join(DATA_DIR, excel_filename)
        else:
            self.excel_path = None

        self.df = None
        self.terminos_dict = {}
        self.nlp = nlp_model if nlp_model is not None else nlp  # Usamos el modelo local o global
        # Cargar el modelo spaCy y definir stopwords
        self.stopwords_spacy = self.nlp.Defaults.stop_words

    def limpiar_espacios(self, cadena):
        """Lógica de la Celda 8: Limpieza de paréntesis y espacios."""
        if not isinstance(cadena, str): return ""
        cadena = re.sub(r'\(\s+', '(', cadena)
        cadena = re.sub(r'\s+\)', ')', cadena)
        return cadena.strip()

    def cargar_datos(self, hoja='Sheet1'):
        """Lógica de carga adaptada para el Excel generado dinámicamente."""
        if self.excel_path and os.path.exists(self.excel_path):
            # Aseguramos que pandas lea el archivo generado por TermExtractor
            self.df = pd.read_excel(self.excel_path, sheet_name=hoja)
            print(f"📊 Datos extraídos cargados. Filas: {len(self.df)}")
        else:
            raise FileNotFoundError(f"❌ Error crítico: No se encontró el Excel de términos en {self.excel_path}")

    def generar_archivos_temporales(self):
        """
        Crea archivos .txt individuales dentro de la carpeta del proyecto.
        """
        if self.df is None: 
            print("No hay datos cargados para generar archivos.")
            return
        
        # Obtenemos términos únicos de la primera columna (Término)
        terminos_unicos = set(self.df.iloc[:, 0].dropna().unique())
        print(f"Generando {len(terminos_unicos)} archivos temporales en: {self.ruta_terminos}")
        
        for i, termino in enumerate(terminos_unicos):
            # Usamos un nombre seguro para el archivo t0, t1, etc.
            ruta_txt = os.path.join(self.ruta_terminos, f"t{i}.txt")
            with open(ruta_txt, "w", encoding="utf-8") as f:
                f.write(str(termino).strip())

    def lematizar_terminos_local(self):
        """
        Sustituye la Celda 7 de Colab. 
        Lematiza los archivos .txt de términos usando el modelo local de spaCy.
        """
        archivos = [f for f in os.listdir(self.ruta_terminos) if f.endswith('.txt')]
        
        if not archivos:
            print("⚠️ No se encontraron archivos para lematizar en la ruta de términos.")
            return

        for nombre in tqdm(archivos, desc="Lematizando términos (spaCy)"):
            path_in = os.path.join(self.ruta_terminos, nombre)
            path_out = os.path.join(self.ruta_lematizados, nombre)
            
            try:
                # 1. Leer el término original
                with open(path_in, 'r', encoding='utf-8') as f:
                    texto = f.read().strip()
                
                if not texto: continue

                # 2. Procesar con spaCy
                # Usamos el modelo cargado en el __init__ (self.nlp)
                doc = self.nlp(texto)
                
                # 3. Extraer lemas (en minúsculas por consistencia)
                lemas = [token.lemma_.lower() for token in doc if not token.is_space]
                cadena_lemas = " ".join(lemas)
                
                # 4. Guardar en la carpeta de lematizados
                with open(path_out, "w", encoding="utf-8") as f_out:
                    f_out.write(cadena_lemas)
                    
            except Exception as e:
                print(f"Error procesando el archivo {nombre}: {e}")


   

    def lematizar_columna_definiciones(self):
        """Versión optimizada para Web: Lematiza definiciones y prepara datos para JSON."""
        if self.df is None: return

        print(f"🧠 Lematizando definiciones para el proyecto: {self.nombre_dic}")
        tqdm.pandas(desc="Procesando definiciones")
        
        def spacy_lemmatizer(texto):
            if pd.isna(texto) or not isinstance(texto, str) or texto.strip() == "":
                return ""
            # Procesamiento con spaCy (usando self.nlp del constructor)
            doc = self.nlp(texto)
            # Retornamos lemas en minúsculas omitiendo espacios
            return " ".join([t.lemma_.lower() for t in doc if not t.is_space])

        self.df['Def_lema'] = self.df['Definiciones'].progress_apply(spacy_lemmatizer)
        self.df['Def_lema'] = self.df['Def_lema'].apply(self.limpiar_espacios)
        print("Lematización completada.")


    def guardar_resultado_excel(self, nombre_salida):
        # Ahora se guarda dentro de la carpeta del diccionario
        ruta_salida = os.path.join(self.project_dir, nombre_salida)
        self.df.to_excel(ruta_salida, index=False)
   
        print(f"Archivo guardado en: {ruta_salida}")
    
    def limpiar_espacios_multipalabras(self, cadena):
        """Lógica de la Celda 8: Limpieza y unión de palabras con '_'."""
        if not isinstance(cadena, str): return ""
        cadena = re.sub(r'\(\s+', '(', cadena)
        cadena = re.sub(r'\s+\)', ')', cadena)
        cadena = cadena.strip()
        # Reemplaza espacios por guiones bajos para términos compuestos
        return cadena.replace(" ", "_")

    def crear_diccionario_mapeo(self):
        """
        Genera el mapeo y lo exporta a un archivo JSON para uso del sistema web.
        """
        archivos = [f for f in os.listdir(self.ruta_terminos) if f.endswith('.txt')]
        for nombre in archivos:
            p_orig = os.path.join(self.ruta_terminos, nombre)
            p_lema = os.path.join(self.ruta_lematizados, nombre)
            if os.path.exists(p_lema):
                with open(p_orig, "r", encoding="utf-8") as f1, \
                     open(p_lema, "r", encoding="utf-8") as f2:
                    original = f1.read().strip()
                    # Normalizamos para detectar multipalabras con espacios
                    lematizado = f2.read().strip().replace("_", " ")
                    self.terminos_dict[original] = lematizado
        
        # --- NUEVA LÓGICA DE EXPORTACIÓN JSON ---
        ruta_json_mapping = os.path.join(self.project_dir, 'mapeo_terminos.json')
        with open(ruta_json_mapping, "w", encoding="utf-8") as f_json:
            json.dump(self.terminos_dict, f_json, ensure_ascii=False, indent=2)
            
        print(f"Diccionario cargado ({len(self.terminos_dict)} entradas) y exportado a JSON.")

    def mapear_terminos_a_columna(self):
        """
        Crea la columna 'term_lema' y valida la integridad del diccionario 
        para la aplicación web.
        """
        if self.df is None: return
        
        # Mapeo seguro usando el diccionario interno cargado
        self.df['term_lema'] = self.df['Término'].apply(lambda x: self.terminos_dict.get(str(x), ""))
        
        # Validación de integridad para el reporte de la aplicación
        faltantes = [term for term in self.df["Término"].dropna().unique() if term not in self.terminos_dict]
        
        if faltantes:
            print(f"Alerta: {len(faltantes)} términos no tienen lema asignado.")
            # Guardamos una lista de errores para que la interfaz web pueda mostrarla
            self.errores_mapeo = faltantes 
        else:
            print("Todos los términos únicos fueron mapeados correctamente.")

    def remover_stopwords_y_limpiar(self, texto):
        """Limpia puntuación y remueve stopwords usando spaCy."""
        if not isinstance(texto, str) or texto.strip() == "":
            return ""
        
        # 1. Limpieza de puntuación y normalización básica
        texto = texto.lower().strip()
        texto = re.sub(r'[^\w\s]', '', texto)
        
        # 2. Tokenización y filtrado de stopwords con spaCy
        doc = self.nlp(texto)
        
        # Filtramos tokens que no sean stopwords y tengan longitud mínima
        tokens_finales = [
            token.text for token in doc 
            if token.text not in self.stopwords_spacy and len(token.text) > 2
        ]
        
        return " ".join(tokens_finales)

    def procesar_definiciones_final(self):
        """
        Limpia stopwords y prepara la base de datos de tripletas semánticas 
        para el archivo JSON final.
        """
        if self.df is None: return

        print("🧹 Eliminando stopwords y extrayendo conocimiento...")
        tqdm.pandas(desc="Limpiando definiciones")
        
        # 1. Limpieza de stopwords (usa método remover_stopwords_y_limpiar)
        self.df['def_lema_limpia'] = self.df['Def_lema'].progress_apply(self.remover_stopwords_y_limpiar)
        
        # 2. Generación de tripletas para el JSON maestro (Compatibilidad con c3.py)
        # Creamos una lista de diccionarios con la estructura: Source, Edge, Target
        self.tripletas_semanticas = []
        for _, fila in self.df.iterrows():
            if fila['term_lema'] and fila['def_lema_limpia']:
                self.tripletas_semanticas.append({
                    "Source": fila['term_lema'],
                    "Edge": "DEFINICIÓN", # Etiqueta genérica para el grafo
                    "Target": fila['def_lema_limpia']
                })
        
        print(f"Conocimiento extraído: {len(self.tripletas_semanticas)} tripletas listas.")
    
    # --- NUEVOS MÉTODOS SECCIÓN 2 ---

    def procesar_y_guardar_geco(self, docs_seleccionados, corpus_id):
        """Descarga de Geco3 y registro de metadatos del corpus."""
        if not self.client_geco: return

        # Registro de documentos para el JSON de auditoría
        self.metadatos_corpus = {
            "corpus_id": corpus_id,
            "documentos": docs_seleccionados,
            "total_docs": len(docs_seleccionados)
        }

        print(f"📥 Descargando y limpiando {len(docs_seleccionados)} documentos...")
        for d in tqdm(docs_seleccionados, desc="Geco -> Local"):
            try:
                contenido = self.client_geco.doc_content(corpus_id, d['id'])
                # Limpieza de escape y puntuación
                contenido_limpio = re.sub(r'\\.', ' ', contenido)
                contenido_limpio = re.sub(r'[^\w\s]', '', contenido_limpio)
                
                ruta_salida = os.path.join(self.geco_limpio, d['archivo'])
                with open(ruta_salida, 'w', encoding='utf-8') as f:
                    f.write(contenido_limpio)
            except Exception as e:
                print(f"Error en {d['archivo']}: {e}")


    def dividir_corpus_geco(self, palabras_por_parte=3000):
        """
        Divide los archivos limpios en partes más pequeñas para la API.
        Lógica de la Celda 6.
        """
        archivos = [f for f in os.listdir(self.geco_limpio) if f.endswith('.txt')]
        print(f"Dividiendo {len(archivos)} archivos en bloques de {palabras_por_parte} palabras...")
        
        for nombre in archivos:
            ruta_archivo = os.path.join(self.geco_limpio, nombre)
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                palabras = f.read().split()
            
            if len(palabras) > palabras_por_parte:
                partes = [palabras[i:i+palabras_por_parte] for i in range(0, len(palabras), palabras_por_parte)]
                for idx, parte in enumerate(partes):
                    nueva_ruta = os.path.join(self.geco_limpio, f"{nombre}_parte{idx+1}.txt")
                    with open(nueva_ruta, 'w', encoding='utf-8') as nf:
                        nf.write(" ".join(parte))
                # Opcional: eliminar el archivo original grande para que no se lematice doble
                os.remove(ruta_archivo)

    def lematizar_corpus_geco(self):
        """
        Sustituye la lematización de FreeLing por spaCy local.
        Procesa los archivos de Geco_limpio y guarda el resultado en Geco_lematizado.
        """
        # Obtenemos la lista de archivos TXT en la carpeta de corpus limpio
        archivos = [f for f in os.listdir(self.geco_limpio) if f.endswith('.txt')]
        
        if not archivos:
            print("No hay archivos en Geco_limpio para procesar.")
            return

        for archivo in tqdm(archivos, desc="Lematizando Corpus con spaCy"):
            path_in = os.path.join(self.geco_limpio, archivo)
            path_out = os.path.join(self.geco_lematizado, archivo)
            
            try:
                # 1. Leer el contenido del archivo descargado de Geco3
                with open(path_in, 'r', encoding='utf-8') as f:
                    contenido = f.read()
                
                if not contenido.strip():
                    continue

                # 2. Procesar con spaCy (Local)
                # nlp.pipe es más eficiente para textos largos si decides usarlo, 
                # pero con self.nlp(contenido) es suficiente para archivos individuales.
                doc = self.nlp(contenido)
                
                # 3. Extraer lemas, convertir a minúsculas y omitir espacios/puntuación
                # Esto garantiza que el corpus esté "limpio" para el generador de grafos.
                lemas = [token.lemma_.lower() for token in doc if not token.is_space and not token.is_punct]
                cadena = " ".join(lemas)
                
                # 4. Guardar el corpus lematizado
                with open(path_out, "w", encoding="utf-8") as f_out:
                    f_out.write(cadena)
                    
            except Exception as e:
                print(f"Error lematizando el archivo del corpus {archivo}: {e}")
    
    # --- MÉTODOS SECCIÓN 3: TÉRMINOS MULTIPALABRA ---

    def cargar_todo_el_corpus_lematizado(self):
        """Lógica de la Celda 2: Lee todos los archivos lematizados y los une."""
        textos = []
        archivos = [f for f in os.listdir(self.geco_lematizado) if f.endswith('.txt')]
        
        print(f"Uniendo {len(archivos)} archivos del corpus lematizado...")
        for nombre in archivos:
            ruta = os.path.join(self.geco_lematizado, nombre)
            with open(ruta, "r", encoding="utf-8") as f:
                textos.append(f.read())
        
        self.corpus_final_unido = " ".join(textos)
        print(f"Corpus total cargado. Caracteres: {len(self.corpus_final_unido)}")

    def verificar_presencia_terminos(self):
        """Lógica de las Celdas 3 y 4: Cuenta cuántos términos aparecen en el corpus."""
        if not self.terminos_dict:
            print("El diccionario de mapeo está vacío.")
            return

        # Obtenemos los lemas (valores del diccionario)
        lemas_a_buscar = list(self.terminos_dict.values())
        si, no = 0, 0
        
        print("Verificando presencia de términos en el corpus...")
        for lema in lemas_a_buscar:
            if lema in self.corpus_final_unido:
                si += 1
            else:
                no += 1
        
        print(f"Resultado: {si} términos presentes, {no} ausentes.")

    def _replace_compound_words(self, text, word_list):
        """Versión blindada: solo reemplaza coincidencias exactas de la lista."""
        if not word_list: return text
        
        # 1. Escapamos caracteres especiales y creamos el patrón
        # El uso de \b asegura que solo se unan palabras completas
        escaped_word_list = [re.escape(word) for word in word_list]
        pattern = r'\b(' + '|'.join(escaped_word_list) + r')\b'

        def replace_spaces(match):
            # Solo reemplazamos espacios por guiones en lo que coincidió
            return match.group(0).replace(' ', '_')

        # 2. Aplicamos sobre el texto
        return re.sub(pattern, replace_spaces, text)
    


    def depurar_lemas_no_deseados(self):
        """
        Elimina guiones bajos de palabras que NO son términos médicos.
        """
        if not self.terminos_dict:
            return

        print("🧹 Depurando posibles falsos multipalabras...")
        # Normalizamos tus lemas a minúsculas para comparar
        lemas_validos = {str(v).lower() for v in self.terminos_dict.values()}
    
        # Buscamos palabras con guion bajo
        palabras_con_guion = set(re.findall(r'\w+_\w+(?:_\w+)*', self.corpus_final_unido))
    
        contador = 0
        for palabra in palabras_con_guion:
            # Si NO es un término médico, lo separamos
            if palabra.lower() not in lemas_validos:
                palabra_con_espacios = palabra.replace('_', ' ')
                self.corpus_final_unido = self.corpus_final_unido.replace(palabra, palabra_con_espacios)
            contador += 1
    
        print(f"Depuración terminada. Se separaron {contador} frases no deseadas.")
    

    def procesar_multipalabras_en_corpus(self):
        """Fuerza la unión de términos multipalabra en el corpus final."""
        if not self.terminos_dict:
            print("❌ ERROR: Diccionario vacío.")
            return

        # Buscamos términos que tengan espacios (ej: 'análisis de sangre')
        lemas_a_unir = [str(v) for v in self.terminos_dict.values() if " " in str(v)]
        
        # DEBUG para ti:
        print(f"DEBUG: Términos con espacios encontrados: {len(lemas_a_unir)}")
        if lemas_a_unir:
            print(f"Ejemplo de términos a unir: {lemas_a_unir[:3]}")

        if lemas_a_unir:
            # Ordenar por longitud para no romper frases anidadas
            lemas_a_unir.sort(key=len, reverse=True)
            self.corpus_final_unido = self._replace_compound_words(self.corpus_final_unido, lemas_a_unir)
            print(f"Reemplazo completado con {len(lemas_a_unir)} patrones.")

    def guardar_corpus_final(self, nombre_archivo="datos_corpus.json"):
        """
        Exporta el corpus procesado y los términos identificados a JSON.
        Esto facilita que cualquier motor de búsqueda cargue los datos.
        """
        ruta_salida = os.path.join(self.project_dir, nombre_archivo)
        
        # Estructura de datos preparada para el nuevo motor de búsqueda
        data_bundle = {
            "proyecto": self.nombre_dic,
            "corpus_unido_lematizado": self.corpus_final_unido,
            "terminos_detectados": [t for t in self.terminos_dict.values() if t in self.corpus_final_unido],
            "mapeo_completo": self.terminos_dict,
            "metadata": getattr(self, 'metadatos_corpus', {})
        }

        with open(ruta_salida, "w", encoding="utf-8") as f:
            json.dump(data_bundle, f, ensure_ascii=False, indent=2)
            
        print(f"Corpus y metadatos exportados a: {ruta_salida}")
    


# ---------------------------
# CONSTRUCCIÓN DEL GRAFO (GraphBuilder) (para API Flask/app.py)
# ---------------------------


class GraphBuilder:
    def __init__(self, nombre_diccionario, nlp_model):
        self.nombre_dic = nombre_diccionario.replace(" ", "_")
        self.project_dir = os.path.join(GRAPH_DIR, self.nombre_dic)
        self.normas_dir = os.path.join(self.project_dir, "normas")
        

        self.data_dir = DATA_DIR 
        self.nlp = nlp_model
        
        os.makedirs(self.normas_dir, exist_ok=True)
        self.grafo = None
        self.vocab_freq = Counter() # Para compatibilidad con c3.py


        self.nlp = nlp_model
        # Preparar NLTK
        nltk.download('punkt', quiet=True)
        nltk.download('stopwords', quiet=True)
        self.vacias = stopwords.words('spanish')




    # SECCIÓN 4. GRAFO COOCURRENCIAS

    def limpiar_y_preparar_texto(self, ruta_entrada):
        """
        Limpia el texto filtrando por categorías gramaticales (POS) 
        procesando por bloques para evitar errores de memoria [E088].
        """
        print("🧼 Filtrando categorías gramaticales (NOUN, ADJ, VERB) por bloques...")
    
        if not os.path.exists(ruta_entrada):
            raise FileNotFoundError(f"No se encontró el archivo: {ruta_entrada}")

        with open(ruta_entrada, 'r', encoding="utf-8") as f:
            data = json.load(f)
            contenido = data.get("corpus_unido_lematizado", "").strip()

        # Categorías con carga semántica real
        pos_permitidos = ["NOUN", "ADJ", "VERB", "PROPN"]
    
        # --- PROCESAMIENTO SEGURO POR BLOQUES ---
        # Dividimos el texto en partes de 500,000 caracteres para no saturar la RAM
        tamano_chunk = 500000
        chunks = [contenido[i:i + tamano_chunk] for i in range(0, len(contenido), tamano_chunk)]
    
        tokens_filtrados = []
    
        # Procesamos cada bloque de forma independiente
        for i, chunk in enumerate(chunks):
            print(f"   ⚙️ Procesando bloque {i+1} de {len(chunks)}...")
            doc = self.nlp(chunk)
        
            for token in doc:
                if (not token.is_stop and 
                    not token.is_punct and 
                    token.pos_ in pos_permitidos and 
                    len(token.text) > 2 and 
                    not token.text.isdigit() and 
                    token.text.lower() != "índice"):
                
                    tokens_filtrados.append(token.text)

        cadena_final = " ".join(tokens_filtrados)
    
        # Guardamos el respaldo limpio
        ruta_salida = os.path.join(self.project_dir, "corpus_completo_lematizado_limpio.txt")
        with open(ruta_salida, "w", encoding="utf-8") as f_out:
            f_out.write(cadena_final)
    
        print(f"Texto filtrado con éxito. Nodos potenciales: {len(tokens_filtrados)}")
        return cadena_final



    def construir_grafo(self, texto_final, window_size=10):
        """Usa las rutas parametrizadas en el __init__."""
        input_text_docs = [{"id": 1, "doc": texto_final}]

        to_cooccurrence = Cooccurrence(
            graph_type='Graph', apply_prep=False, parallel_exec=True,
            window_size=window_size, language='sp', output_format='networkx'
        )

        output_text_graphs = to_cooccurrence.transform(input_text_docs)
        self.grafo = output_text_graphs[0]['graph']
        
        # Eliminar todas las aristas cuyo weight sea igual a 1 (conexiones únicas) para limpiar ruido
        aristas_a_eliminar = [(u, v) for u, v, d in self.grafo.edges(data=True) if d.get('weight', 0) == 1]
        self.grafo.remove_edges_from(aristas_a_eliminar)
        
        # Guardamos el .gexf dentro de la carpeta del proyecto
        ruta_gexf = os.path.join(self.project_dir, f"grafo_ventana{window_size}.gexf")
        nx.write_gexf(self.grafo, ruta_gexf)
        return self.grafo
    
    # SECCIÓN 5. NORMAS

    def generar_normas_asociacion(self, terminos_dict):
        """
        Consolida todas las normas en un solo objeto JSON en lugar de múltiples CSVs.
        """
        if self.grafo is None: return

        # Diccionario maestro de normas: { 'termino': [ {res, freq, asoc}, ... ] }
        normas_consolidadas = {}
        pesos_aristas = nx.get_edge_attributes(self.grafo, 'freq')
        
        terminos_unidos = [t.replace(" ", "_") for t in terminos_dict.values()]

        for term in tqdm(terminos_unidos, desc="Consolidando Normas"):
            if term in self.grafo:
                vecinos = list(self.grafo.neighbors(term))
                suma_total = sum([int(pesos_aristas.get((v, term), pesos_aristas.get((term, v), 0))) 
                                 for v in vecinos if v != term])

                if suma_total == 0: continue

                asociaciones = []
                for v in vecinos:
                    if v != term:
                        p_local = int(pesos_aristas.get((v, term), pesos_aristas.get((term, v), 0)))
                        asociaciones.append({
                            "Respuesta": v,
                            "Frecuencia": p_local,
                            "Asociación": float(p_local / suma_total)
                        })
                
                # Ordenar por frecuencia y guardar en el diccionario maestro
                normas_consolidadas[term] = sorted(asociaciones, key=lambda x: x['Frecuencia'], reverse=True)

        # GUARDADO FINAL EN JSON
        ruta_json_normas = os.path.join(self.project_dir, 'normas_asociacion.json')
        with open(ruta_json_normas, "w", encoding="utf-8") as f:
            json.dump(normas_consolidadas, f, ensure_ascii=False, indent=2)
            
        print(f"Normas consolidadas en: {ruta_json_normas}")
        return normas_consolidadas

    # 6. GALEX
    
    def remover_nodos_vacios(self, grafo, nombre_archivo_vacias="removed_words.txt"):
        """
        Lógica de la Celda 1: Elimina nodos manuales (filtros extra) del grafo.
        """
        ruta_vacias = os.path.join(self.data_dir, nombre_archivo_vacias)
        
        if not os.path.exists(ruta_vacias):
            print(f"No se encontró {nombre_archivo_vacias}, se saltará la eliminación manual.")
            return grafo

        print(f"🧹 Removiendo nodos especificados en {nombre_archivo_vacias}...")
        with open(ruta_vacias, "r", encoding="utf-8") as f:
            palabras = [linea.strip() for linea in f.readlines() if linea.strip()]
        
        nodos_removidos = 0
        for palabra in palabras:
            if palabra in grafo.nodes():
                grafo.remove_node(palabra)
                nodos_removidos += 1
        
        print(f"Se removieron {nodos_removidos} nodos del grafo.")
        return grafo

    def construir_grafos_galex(self):
        """Lee el JSON maestro para construir los grafos maestros A y F."""
        ruta_json_normas = os.path.join(self.project_dir, 'normas_asociacion.json')
        
        with open(ruta_json_normas, "r", encoding="utf-8") as f:
            normas = json.load(f)

        grafo_a = nx.Graph()
        grafo_f = nx.Graph()

        for estimulo, respuestas in normas.items():
            for resp in respuestas:
                # Lógica Galex (Celda 2)
                grafo_f.add_edge(estimulo, resp['Respuesta'], weight=float(1/resp['Frecuencia']))
                grafo_a.add_edge(estimulo, resp['Respuesta'], weight=float(1 - resp['Asociación']))

        # Guardado de grafos maestros del proyecto
        nx.write_gexf(grafo_a, os.path.join(self.project_dir, "grafo_asociacion.gexf"))
        nx.write_gexf(grafo_f, os.path.join(self.project_dir, "grafo_frecuencia.gexf"))
        
        return grafo_a, grafo_f



class ReverseDict:
    def __init__(self, nombre_diccionario, nlp_model):
        """
        Inicializa el motor cargando el grafo y las normas desde el JSON maestro.
        """
        self.nombre_dic = nombre_diccionario.replace(" ", "_")
        self.project_dir = os.path.join(GRAPH_DIR, self.nombre_dic)
        self.nlp = nlp_model
        
        # 1. Cargar Grafo de Asociación (el .gexf final de Galex)
        ruta_grafo = os.path.join(self.project_dir, "grafo_asociacion.gexf")
        if os.path.exists(ruta_grafo):
            self.grafo = nx.read_gexf(ruta_grafo)
        else:
            raise FileNotFoundError(f"No se encontró el grafo en {ruta_grafo}")

        # 2. Cargar Normas Consolidadas (el JSON que reemplaza a los CSV)
        ruta_normas = os.path.join(self.project_dir, "normas_asociacion.json")
        with open(ruta_normas, "r", encoding="utf-8") as f:
            self.normas_maestras = json.load(f)

    def limpiar_y_lematizar(self, texto):
        """Normaliza la consulta del usuario."""
        doc = self.nlp(texto.lower())
        return [token.lemma_ for token in doc if token.is_alpha and not token.is_stop]


    def buscar(self, query, n_sugerencias=20):
        """
        Motor de búsqueda mejorado con Activación Propagada y 
        re-ranking por coincidencia múltiple.
        """
        # 1. Normalización y filtrado de la consulta
        lemas_consulta = [p for p in self.limpiar_y_lematizar(query) if p in self.grafo.nodes()]
    
        if not lemas_consulta:
            return None

        # Diccionario para acumular el score de cada candidato
        # { nodo_candidato: { 'score': float, 'coincidencias': int } }
        scores = defaultdict(lambda: {'score': 0.0, 'coincidencias': 0})

        # 2. FASE DE ACTIVACIÓN: Propagar energía desde los lemas de consulta
        for lema in lemas_consulta:
            if lema in self.grafo:
                # Obtenemos vecinos directos del lema de consulta
                vecinos = self.grafo[lema]
                for vecino, data in vecinos.items():
                    if vecino in lemas_consulta:
                        continue
                
                    # En Galex (Asociación), un 'weight' menor suele significar 
                    # una relación más fuerte (distancia). Invertimos para obtener score.
                    weight = data.get('weight', 1.0)
                    # Evitamos división por cero y suavizamos la curva
                    score_incremental = 1.0 / (weight + 0.001)
                
                    scores[vecino]['score'] += score_incremental
                    scores[vecino]['coincidencias'] += 1

        # 3. FASE DE FILTRADO Y PENALIZACIÓN
        candidatos_finales = []
        for cand, data in scores.items():
            score_base = data['score']
            n_coincidencias = data['coincidencias']
        
            # --- MEJORA: Bonus por Coincidencia Múltiple ---
            # Si un término se relaciona con 2 o más palabras de la consulta, 
            # su relevancia crece exponencialmente.
            if n_coincidencias > 1:
                score_final = score_base * (n_coincidencias ** 2)
            else:
                # Penalizamos términos que solo se conectan a una sola palabra 
                # de la consulta para evitar ruido.
                score_final = score_base * 0.5
            
            candidatos_finales.append((cand, score_final))

        # 4. RE-RANKING SEMÁNTICO POR ASOCIACIÓN (Normas_asociacion.json)
        # Refinamos el top de candidatos usando los pesos de probabilidad del JSON
        ranking_refinado = []
        # Tomamos un pool amplio de candidatos para el re-ranking
        top_candidatos = sorted(candidatos_finales, key=itemgetter(1), reverse=True)[:50]

        for cand, score_grafo in top_candidatos:
            peso_asociacion = 0.0
            if cand in self.normas_maestras:
                # Convertimos las respuestas de las normas a un mapa de consulta rápida
                mapa_asoc = {r['Respuesta']: r['Asociación'] for r in self.normas_maestras[cand]}
            
                for palabra in lemas_consulta:
                    if palabra in mapa_asoc:
                        # Sumamos la probabilidad de asociación directa
                        peso_asociacion += float(mapa_asoc[palabra])
        
            # El score final es un híbrido entre la energía del grafo y la asociación estadística
            score_hibrido = (score_grafo * 0.7) + (peso_asociacion * 100 * 0.3)
            ranking_refinado.append((cand, score_hibrido))

        # 5. Ordenar y retornar los mejores resultados
        resultados = sorted(ranking_refinado, key=itemgetter(1), reverse=True)
        return [res[0] for res in resultados[:n_sugerencias]]

# --------------------------------------------
#   FUNCIONES PARA GESTIÓN DE DICCIONARIOS
# --------------------------------------------

def guardar_diccionario(nombre_diccionario, grafo, base_de_datos, builder, owner="Anónimo"):
    """
    Guarda el proyecto completo en su carpeta y actualiza el índice global.
    """
    base_name = nombre_diccionario.replace(" ", "_")
    project_dir = os.path.join(GRAPH_DIR, base_name)
    os.makedirs(project_dir, exist_ok=True)

    archivo_json_maestro = f"{base_name}.json"
    ruta_json_maestro = os.path.join(project_dir, archivo_json_maestro)

    # Datos maestros para el buscador
    data_maestra = {
        "nombre": nombre_diccionario,
        "nodes": list(grafo.nodes(data=True)),
        "edges": list(grafo.edges(data=True)),
        "base_de_datos": base_de_datos,
        "vocab_freq": dict(builder.vocab_freq)
    }

    with open(ruta_json_maestro, "w", encoding="utf-8") as f:
        json.dump(data_maestra, f, ensure_ascii=False, indent=2)

    # Actualización del índice diccionarios_index.json
    index_path = os.path.join(GRAPH_DIR, "diccionarios_index.json")
    index = []
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

    index = [d for d in index if d["nombre"] != nombre_diccionario]
    index.append({
        "nombre": nombre_diccionario,
        "owner": owner,
        "archivo_maestro": os.path.join(base_name, archivo_json_maestro),
        "normas_json": os.path.join(base_name, "normas_asociacion.json"),
        "grafo_asociacion": os.path.join(base_name, "grafo_asociacion.gexf"),
        "n_nodos": grafo.number_of_nodes(),
        "n_tripletas": len(base_de_datos)
    })

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"Diccionario '{nombre_diccionario}' registrado con éxito.")


def cargar_diccionario(nombre_diccionario, nlp_model):
    """
    Carga el grafo y datos semánticos desde la subcarpeta del proyecto.
    """
    index_path = os.path.join(GRAPH_DIR, "diccionarios_index.json")
    if not os.path.exists(index_path):
        return None, None, None, None

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    dic_entry = next((d for d in index if d["nombre"] == nombre_diccionario), None)
    if not dic_entry:
        return None, None, None, None

    # IMPORTANTE: La ruta ahora es relativa a GRAPH_DIR (ej: Medicina/Medicina.json)
    ruta_json = os.path.join(GRAPH_DIR, dic_entry["archivo_maestro"])
    
    if not os.path.exists(ruta_json):
        print(f"❌ Error: No se encontró el archivo maestro en {ruta_json}")
        return None, None, None, None

    with open(ruta_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Reconstruir Grafo NetworkX (Asociación)
    G = nx.Graph()
    # Intentamos cargar el grafo de asociación Galex primero
    ruta_grafo_asoc = os.path.join(GRAPH_DIR, dic_entry.get("grafo_asociacion", ""))
    
    if os.path.exists(ruta_grafo_asoc) and dic_entry.get("grafo_asociacion"):
        try:
            G = nx.read_gexf(ruta_grafo_asoc)
            # Asegurar que los nodos tengan metadata frequency para que el frontend no falle
            vocab_freq = data.get("vocab_freq", {})
            for n in G.nodes():
                if 'frequency' not in G.nodes[n]:
                    G.nodes[n]['frequency'] = vocab_freq.get(n, 1)
        except Exception as e:
            print(f"⚠️ Error cargando {ruta_grafo_asoc}: {e}. Cayendo al JSON.")
            G = nx.Graph()
            G.add_nodes_from(data["nodes"])
            G.add_edges_from(data["edges"])
    else:
        G.add_nodes_from(data["nodes"])
        G.add_edges_from(data["edges"])

    # 2. Restaurar Base de Datos Semántica (Tripletas)
    base_de_datos = data.get("base_de_datos", [])

    # 3. Restaurar Clases con las nuevas firmas (incluyendo el nombre del dic)
    # Nota: Pasamos None al excel porque ya estamos cargando datos procesados
    processor = TextProcessor(None, nombre_diccionario, nlp_model=nlp_model)
    builder = GraphBuilder(nombre_diccionario, nlp_model)
    builder.vocab_freq = Counter(data.get("vocab_freq", {}))
    builder.grafo = G

    print(f"Proyecto '{nombre_diccionario}' cargado desde su carpeta.")
    return G, base_de_datos, processor, builder




import shutil # Necesario para borrar carpetas completas
def borrar_diccionario(nombre_diccionario, usuario_solicitante):
    """
    Elimina la carpeta completa del proyecto y su entrada en el índice.
    """
    index_path = os.path.join(GRAPH_DIR, "diccionarios_index.json")
    if not os.path.exists(index_path):
        return False, "No existen registros de diccionarios."

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    target = next((d for d in index if d["nombre"] == nombre_diccionario), None)
    if not target:
        return False, "Diccionario no encontrado."

    # Validación de seguridad (Owner)
    if target.get("owner") and target.get("owner") != usuario_solicitante:
        return False, f"Permiso denegado. El dueño es {target.get('owner')}."

    # 1. Eliminar la CARPETA completa del proyecto
    # Obtenemos el nombre de la carpeta desde el nombre del diccionario
    folder_name = nombre_diccionario.replace(" ", "_")
    project_path = os.path.join(GRAPH_DIR, nombre_diccionario.replace(" ", "_"))

    def on_rm_error(func, path, exc_info):
        """Manejador para archivos que Windows se niega a borrar"""
        import stat
        os.chmod(path, stat.S_IWRITE)
        func(path)

    try:
        if os.path.exists(project_path):
            # Usamos el manejador de errores para forzar permisos
            shutil.rmtree(project_path, onerror=on_rm_error)
            print(f"Carpeta {project_path} eliminada.")
    except Exception as e:
        return False, f"Error al eliminar archivos físicos: {e}"

    # 2. Actualizar índice global
    index = [d for d in index if d["nombre"] != nombre_diccionario]
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return True, f"Diccionario '{nombre_diccionario}' eliminado totalmente."
    


def finalizar_y_registrar_diccionario(processor, builder, nombre_usuario="Anónimo"):
    """
    Consolida tripletas y grafo para llamar al guardado final.
    """
    print(f"\nConsolidando paquete final para: {builder.nombre_dic}...")
    
    # Extraemos las tripletas generadas en TextProcessor
    base_de_datos = getattr(processor, 'tripletas_semanticas', [])
    
    # LLAMADA SINCRONIZADA: usamos 'grafo'
    guardar_diccionario(
        nombre_diccionario=builder.nombre_dic,
        grafo=builder.grafo, 
        base_de_datos=base_de_datos,
        builder=builder,
        owner=nombre_usuario
    )



# --------------------------------------------
#   Función para ejecutar el pipeline completo - app.py
# --------------------------------------------

def ejecutar_pipeline_completo(nombre_dic, corpus_id, doc_ids, client, nlp_model, nombre_user="Anónimo", status_callback=None):
    """
    Orquestador principal con reporte de progreso en tiempo real.
    """
    # Esta función interna envía el mensaje a la terminal Y a la web
    def reportar(msg):
        print(msg)
        if status_callback:
            status_callback(msg)

    try:
        # --- CONFIGURACIÓN INICIAL ---
        nombre_seguro = nombre_dic.replace(" ", "_")
        project_dir = os.path.join(GRAPH_DIR, nombre_seguro)
        os.makedirs(project_dir, exist_ok=True)
        
        ruta_excel = os.path.join(project_dir, "terminos_definiciones.xlsx")
        
        # --- FASE 1: EXTRACCIÓN DINÁMICA ---
        reportar(f"🔍 Fase 1: Extrayendo términos del corpus {corpus_id}...")
        textos_para_extractor = []
        for d_id in doc_ids:
            contenido = client.doc_content(corpus_id, d_id)
            textos_para_extractor.append({'texto': contenido})
        
        extractor = TermExtractor(nlp_model)
        extractor.extraer_a_excel(textos_para_extractor, ruta_excel)
        
        if not os.path.exists(ruta_excel):
            raise Exception("El extractor no pudo encontrar definiciones claras en el corpus.")

        # --- FASE 2: PROCESAMIENTO DE TEXTO ---
        reportar(f"🧠 Fase 2: Procesando términos y lematizando para '{nombre_dic}'...")
        processor = TextProcessor(ruta_excel, nombre_dic, client_geco=client, nlp_model=nlp_model)
        
        processor.cargar_datos()
        processor.generar_archivos_temporales()
        processor.lematizar_terminos_local()
        processor.crear_diccionario_mapeo()
        processor.mapear_terminos_a_columna()
        processor.lematizar_columna_definiciones()
        processor.procesar_definiciones_final()

        reportar("📂 Descargando y preparando documentos del corpus físico...")
        all_docs = client.docs_corpus(corpus_id)
        docs_seleccionados = [d for d in all_docs if d['id'] in doc_ids]
        
        processor.procesar_y_guardar_geco(docs_seleccionados, corpus_id)
        
        reportar("✂️ Dividiendo y lematizando el corpus en bloques...")
        processor.dividir_corpus_geco(palabras_por_parte=3000)
        processor.lematizar_corpus_geco()
        
        reportar("🔗 Consolidando multipalabras y depurando lemas...")
        processor.cargar_todo_el_corpus_lematizado()
        processor.depurar_lemas_no_deseados()
        processor.procesar_multipalabras_en_corpus()
        processor.guardar_corpus_final()

        # --- FASE 3: CONSTRUCCIÓN DE GRAFOS ---
        reportar("🧹 Fase 3: Limpiando texto para el grafo (POS Tagging)...")
        builder = GraphBuilder(nombre_dic, nlp_model)
        ruta_json_corpus = os.path.join(processor.project_dir, "datos_corpus.json")
        texto_grafo = builder.limpiar_y_preparar_texto(ruta_json_corpus)
        
        reportar("🕸️ Construyendo grafo de coocurrencia y normas de asociación...")
        builder.construir_grafo(texto_grafo)
        builder.generar_normas_asociacion(processor.terminos_dict)
        
        reportar("📈 Generando grafos finales Galex...")
        builder.construir_grafos_galex()

        # --- FASE 4: REGISTRO FINAL ---
        reportar(f"📦 Fase 4: Registrando diccionario en el índice...")
        finalizar_y_registrar_diccionario(processor, builder, nombre_usuario=nombre_user)
        
        reportar(f"🎉Diccionario '{nombre_dic}' creado exitosamente.")
        return True, f"Diccionario '{nombre_dic}' creado exitosamente."

    except Exception as e:
        reportar(f"❌ Error en el pipeline: {str(e)}")
        return False, str(e)



# --------------------------------------------
#   Ejecución del script en terminal 
# --------------------------------------------


if __name__ == "__main__":
    # 1. Configuración de Clientes y Entrada
    config = load_config()
    client = get_client(token=config.get("user_token"))
    
    print("=" * 60)
    print("SISTEMA DE DICCIONARIO INVERSO")
    print("=" * 60)

    # Preguntar si procesar nuevo o usar uno existente
    opcion_inicio = input("1. Procesar nuevo diccionario\n2. Cargar diccionario existente\n> ")

    if opcion_inicio == "1":
        nombre_dic = input("Nombre del nuevo diccionario: ").strip()
        # (Processor, Builder, Geco, etc.)
        finalizar_y_registrar_diccionario(processor, builder, "Admin_Ismael")
    else:
        # Listar disponibles desde el índice
        index_path = os.path.join(GRAPH_DIR, "diccionarios_index.json")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            print("\nDiccionarios disponibles:")
            for i, d in enumerate(index, 1):
                print(f"{i}. {d['nombre']}")
            
            idx_sel = int(input("\nElige el número del diccionario: ")) - 1
            nombre_dic = index[idx_sel]['nombre']
        else:
            print("No hay diccionarios registrados.")
            exit()

    # --- INICIO DEL MOTOR INTERACTIVO ---
    print(f"\n🔍 Inicializando motor de búsqueda para: {nombre_dic}...")
    try:
        buscador = ReverseDict(nombre_dic, nlp)
        print("Base de conocimiento cargada.\n")
        
        while True:
            print("-" * 60)
            user_input = input("Escribe una definición o concepto (o 'salir'): \n> ")
            
            if user_input.lower() in ['salir', 'exit', 'q']:
                break
            
            if not user_input.strip():
                continue

            # Ejecutar búsqueda
            # Agregamos un pequeño log para ver qué está pasando dentro
            lemas_query = buscador.limpiar_y_lematizar(user_input)
            presentes = [l for l in lemas_query if l in buscador.grafo.nodes()]
            
            print(f"DEBUG: Lemas detectados: {lemas_query}")
            print(f"DEBUG: Lemas en el grafo: {presentes}")

            sugerencias = buscador.buscar(user_input)
            
            if sugerencias:
                print("\nPALABRAS SUGERIDAS:")
                for i, palabra in enumerate(sugerencias, 1):
                    # Intentamos buscar si tenemos una definición en la base de datos
                    print(f"  {i}. {palabra.upper()}")
            else:
                print("\nNo se encontraron términos. ")
                print("Tip: Intenta usar palabras más generales o términos que sepas que están en tu corpus.")

    except Exception as e:
        print(f"Error al cargar el buscador: {e}")

    print("\nSistema cerrado.")


