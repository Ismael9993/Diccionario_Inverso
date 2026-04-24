# Cliente Python para GECO3/4

Este repositorio contiene un cliente Python (`GECO3Client`) para conectarse a la API de **GECO3/4** y consumir los principales endpoints relacionados con:

- Autenticación de **aplicación** y **usuario**.
- Consulta de **corpus** (públicos, privados y asociados a una app).
- Consulta de **documentos** y sus **metadatos**.
- Obtención de contenido plano y contenido etiquetado con POS de los documentos.
- Utilidades de ofuscación de tokens/strings mediante XOR + Base64.

> ⚠️ **Aviso de seguridad**: el esquema de cifrado incluido (XOR + Base64) es **solo una ofuscación ligera**.  
> No debe considerarse un mecanismo criptográfico fuerte ni usarse para proteger información altamente sensible.

---

## Contenido del repositorio

- `geco_client.py` (o el nombre de archivo que definas): implementación de:
  - Clase `GECO3Client`.
  - Funciones auxiliares:
    - `xor_cipher_bytes(data: bytes, key: str) -> bytes`
    - `encript(clave: str, mensaje: str) -> str`
    - `decript(clave: str, cifrado_b64: str) -> str`

Puedes renombrar el archivo principal a `geco_client.py` y ajustar los imports en tus proyectos de acuerdo con ello.

---

## Requisitos

- Python 3.7+  
- Dependencias:

```bash
pip install requests
```

---

## Instalación

1. Clona este repositorio o copia el archivo del cliente en tu proyecto:

```bash
git clone https://github.com/<tu_usuario>/<tu_repo>.git
cd <tu_repo>
```

2. Instala las dependencias (principalmente `requests`):

```bash
pip install -r requirements.txt
# o simplemente
pip install requests
```

3. Importa el cliente en tu código:

```python
from geco_client import GECO3Client, encript, decript
```

> Ajusta el nombre del módulo (`geco_client`) si cambiaste el nombre del archivo.

---

## Descripción general de `GECO3Client`

La clase `GECO3Client` encapsula la lógica para:

- Construir URLs a partir de un `host` base y rutas internas.
- Gestionar tokens de **aplicación** (`app_token`) y de **usuario** (`token`).
- Llamar de forma homogénea a los endpoints de la API.
- Obtener corpus, documentos, metadatos y texto etiquetado POS.

### Atributos principales

- `host`: URL base del servidor GECO3/4 (por ejemplo: `https://mi-servidor-geco3/`).
- `token`: token de autenticación de usuario.
- `app_token`: token de autenticación de aplicación.
- `user_info`: diccionario con información básica del usuario:
  - `name`: nombre visible.
  - `is_anon`: `True` si se trata de usuario anónimo.
- `anon_user`, `anon_pass`: credenciales del usuario anónimo (opcional).
- `app_name`, `app_password`: credenciales de la aplicación (opcional).

### Endpoints manejados internamente

La clase define constantes con las rutas relativas utilizadas:

- `PATH_LOGIN = "proyectos/apidocs/get-token"`
- `PATH_LOGIN_APP = "proyectos/apidocs/get-token-app"`
- `PATH_CORPUS_PUBLICOS = "proyectos/apidocs/corpus/"`
- `PATH_CORPUS_PRIVADOS = "proyectos/apidocs/corpus/colabora"`
- `PATH_CORPUS_APP = "proyectos/apidocs/apps/{app_name}/proyectos"`
- `PATH_DOCS_CORPUS = "proyectos/apidocs/corpus/{id_corpus}"`
- `PATH_DOCS_CORPUS_TABLA = "proyectos/apidocs/corpus/{id_corpus}/tabla"`
- `PATH_TAGGED_DOC = "proyectos/apidocs/corpus/{id_corpus}/{id_doc}/pos"`
- `PATH_TAGGED_DOC_APP = "proyectos/apidocs/apps/{id_corpus}/{id_doc}/pos"`
- `PATH_DOC = "proyectos/apidocs/corpus/{id_corpus}/{id_doc}"`
- `PATH_DOC_APP = "proyectos/apidocs/apps/{id_corpus}/{id_doc}"`
- `PATH_DOC_META = "proyectos/apidocs/corpus/{id_corpus}/{id_doc}/meta"`
- `PATH_DOC_META_APP = "proyectos/apidocs/apps/{id_corpus}/{id_doc}/meta"`
- `PATH_CORPUS_META = "proyectos/apidocs/corpus/{id_corpus}/meta"`

---

## Uso rápido

### Inicialización del cliente

```python
from geco_client import GECO3Client

client = GECO3Client(
    host="https://mi-geco3/",
    anon_user="usuario_anonimo",       # opcional
    anon_pass="password_anonimo",      # opcional
    app_name="mi_app",                 # opcional
    app_password="mi_app_password"     # opcional
)
```

- Si proporcionas `app_name` y `app_password`, el cliente hará automáticamente `login_app()` en el constructor.
- Después podrás usar `client.is_app_logged()` para saber si el login de app fue exitoso.

---

## Autenticación

### Login de aplicación

```python
client.login_app()
print(client.app_token)
```

Internamente llama a:

- `POST proyectos/apidocs/get-token-app`

con el payload:

```json
{
  "nombre": "<app_name>",
  "password": "<app_password>"
}
```

y almacena el `app_token` en `client.app_token`.

---

### Login de usuario

```python
# Caso típico con usuario/contraseña
client.login(username="mi_usuario", password="mi_password")
print(client.token)
print(client.user_info)
```

Comportamiento del método `login`:

1. Si no se proporcionan `username`, `password` ni `token`:
   - Usa `anon_user` y `anon_pass` configurados en el constructor.
2. Si se proporciona un `token`:
   - Se asume login por token, con opción a que venga **encriptada**:
     - Si `is_token_encrypted=True`, la token se descifra con:
       ```python
       token = decript(self.app_token, token_cifrada)
       ```
3. Si aún no hay token válida:
   - Llama a:
     - `POST proyectos/apidocs/get-token`
   - con el payload:
     ```json
     {
       "username": "<username>",
       "password": "<password>"
     }
     ```
   - y guarda el valor de `"token"` en `client.token`.

Además, se llama a `init_user(is_anon)` para inicializar `user_info`.

---

### Usuario anónimo

El comportamiento anónimo se controla así:

- Si `login()` se llama sin parámetros y se configuraron `anon_user` / `anon_pass`, esos se usan.
- La propiedad `user_info["is_anon"]` se marca en consecuencia.
- El nombre por defecto del usuario anónimo es:
  - `"Usuario Anónimo"` (`DISPLAY_NAME_ANONIMO`).

Puedes sobrescribir el nombre visible más tarde:

```python
client.set_user_name("Nombre visible del usuario")
print(client.user_info["name"])
```

---

## Llamadas genéricas a la API

La función interna `call_endpoint(path, method, data=None, headers=None)`:

- Construye `url = host + path`.
- Soporta `GET` y `POST`.
- Manejo básico de errores:
  - Si `status_code == 401`, lanza `Exception("No autorizado: ...")`.
  - Si `resp.ok` es `False`, lanza `Exception("GECO3 respondió con un error: ...")`.
  - Cualquier excepción se encapsula como:
    - `Exception("Error en comunicación con GECO3: ...")`.

Las cabeceras de autenticación se generan con `_get_headers()`:

```python
headers = {}
if self.token:
    headers["Authorization"] = "Token " + self.token
```

---

## Operaciones sobre corpus

### Corpus asociados a la aplicación

```python
proyectos_app = client.corpus_app()
for p in proyectos_app:
    print(p)
```

- Endpoint: `GET proyectos/apidocs/apps/{app_name}/proyectos`
- Devuelve `resp["proyectos"]` o una lista vacía.

### Corpus públicos

```python
corpus_publicos = client.corpus_publicos()
for c in corpus_publicos:
    print(c)
```

- Endpoint: `GET proyectos/apidocs/corpus/`
- Devuelve `resp["data"]["proyectos"]` o una lista vacía.

### Corpus privados (colaboraciones)

```python
corpus_privados = client.corpus_privados()
for c in corpus_privados:
    print(c)
```

- Endpoint: `GET proyectos/apidocs/corpus/colabora`
- Devuelve `resp["data"]["proyectos"]` o una lista vacía.

---

## Operaciones sobre documentos

### Listar documentos de un corpus

```python
docs = client.docs_corpus(id_corpus=123)
for d in docs:
    print(d)
```

- Endpoint: `GET proyectos/apidocs/corpus/{id_corpus}`
- Devuelve `resp.json()["data"]` (formato definido por el servidor).

### Documentos + metadatos en formato tabla

```python
docs_tabla = client.docs_tabla(id_corpus=123)
for doc in docs_tabla:
    print(doc["id"], doc["name"], doc["metadata"])
```

- Endpoint: `GET proyectos/apidocs/corpus/{id_corpus}/tabla`
- Estructura esperada del `JSON` de respuesta:

```json
{
  "data": {
    "metadatos": [
      [id_metadato, nombre_metadato],
      ...
    ],
    "tabla": [
      [id_doc, titulo_doc, metadatos_doc],
      ...
    ]
  }
}
```

donde `metadatos_doc` es una lista de pares:

```text
[id_metadato, valor_metadato]
```

El método genera una lista de diccionarios:

```python
{
  "id": id_doc,
  "name": titulo_doc,
  "metadata": {
    "<nombre_metadato>": <valor_metadato>,
    ...
  }
}
```

---

## Contenido de documentos

### Texto plano de un documento

```python
texto = client.doc_content(id_corpus=123, id_doc=456)
print(texto)
```

Resolución interna del endpoint (`_resolve_doc_content_endpoint`):

- Si hay `app_token`:
  - `POST proyectos/apidocs/apps/{id_corpus}/{id_doc}`
  - con `data = {"app": app_name, "token": app_token}`.
- Si **no** hay `app_token`:
  - `GET proyectos/apidocs/corpus/{id_corpus}/{id_doc}`.

El método `doc_content` devuelve `resp.json()["data"]`.

---

### Texto con etiquetado POS

```python
texto_pos = client.doc_content_pos(id_corpus=123, id_doc=456)
print(texto_pos)
```

Resolución interna del endpoint (`_resolve_doc_content_pos_endpoint`):

- Si hay `app_token`:
  - `POST proyectos/apidocs/apps/{id_corpus}/{id_doc}/pos`
- Si no:
  - `GET proyectos/apidocs/corpus/{id_corpus}/{id_doc}/pos`

La respuesta esperada es algo como:

```json
{
  "data": [
    { "token": "...", "lemma": "...", "tag": "...", "prob": "..." },
    ...
  ]
}
```

El método transforma esa lista en un `str` con formato:

```text
token lemma tag prob
```

y agrega una línea en blanco cada vez que `tag == "Fp"` (p.ej. puntuación final de frase), para separar frases.

---

## Metadatos de un corpus

```python
meta = client.metadatos(id_corpus=123)
print(meta)
```

- Endpoint: `GET proyectos/apidocs/corpus/{id_corpus}/meta`
- Devuelve `resp.json()["data"]`.

---

## Utilidades de ofuscación (XOR + Base64)

En el mismo archivo se incluyen funciones para cifrar/descifrar strings de forma simétrica usando XOR y Base64.  
Son útiles para **ofuscar** valores (por ejemplo, tokens) pero **no** deben considerarse criptografía fuerte.

### `xor_cipher_bytes(data: bytes, key: str) -> bytes`

Realiza un XOR byte a byte entre:

- `data`: bytes del mensaje.
- `key`: clave como string, convertida a bytes UTF-8, repetida tantas veces como sea necesario.

Ejemplo:

```python
from geco_client import xor_cipher_bytes

resultado = xor_cipher_bytes(b"hola", "mi_clave")
print(resultado)
```

### `encript(clave: str, mensaje: str) -> str`

Cifra un mensaje de texto y lo devuelve en base64:

```python
from geco_client import encript

token_plana = "mi_token_super_secreta"
token_cifrada = encript("mi_clave", token_plana)
print(token_cifrada)
```

### `decript(clave: str, cifrado_b64: str) -> str`

Hace la operación inversa:

```python
from geco_client import decript

token_recuperada = decript("mi_clave", token_cifrada)
print(token_recuperada)  # "mi_token_super_secreta"
```

> **Importante:** Quien tenga la clave y la token cifrada puede recuperar la token original.  
> Usa este esquema solo como una capa de ofuscación ligera.

---

## Ejemplo completo

```python
from geco_client import GECO3Client

# 1. Crear cliente
client = GECO3Client(
    host="https://mi-geco3/",
    anon_user="anon",
    anon_pass="anon_pass",
    app_name="mi_app",
    app_password="mi_app_pass"
)

# 2. Login de usuario (opcional, si no quieres usar solo anónimo)
client.login(username="usuario", password="password")
client.set_user_name("Nombre visible del usuario")

# 3. Listar corpus públicos
print("Corpus públicos:")
for corpus in client.corpus_publicos():
    print(corpus)

# 4. Obtener documentos de un corpus
docs = client.docs_corpus(id_corpus=1)
print("Documentos del corpus 1:")
for d in docs:
    print(d)

# 5. Obtener contenido de un documento
texto = client.doc_content(id_corpus=1, id_doc=10)
print("Contenido del documento 10:")
print(texto)

# 6. Obtener contenido etiquetado POS
texto_pos = client.doc_content_pos(id_corpus=1, id_doc=10)
print("Contenido POS del documento 10:")
print(texto_pos)

# 7. Obtener documentos con metadatos en formato tabla
docs_tabla = client.docs_tabla(id_corpus=1)
print("Documentos (vista tabla):")
for doc in docs_tabla:
    print(doc["id"], doc["name"], doc["metadata"])
```

---

## Posibles mejoras

Algunas ideas de evolución del cliente:

- **Validación de token de usuario**: añadir un endpoint dedicado para verificar la token y obtener datos de perfil.
- **Excepciones específicas**: definir clases de excepción propias (`GecoAuthError`, `GecoApiError`, etc.) para manejar mejor los errores.
- **Logging configurable**: reemplazar los `print` por el módulo `logging` y permitir configurar el nivel de detalle.
- **Tests unitarios**: añadir pruebas para las funciones de cifrado, el manejo de respuestas y el formateo de datos.

---

