"""
Cliente para conexión con GECO3/4

"""
import json
import requests
import base64


class GECO3Client:
    DISPLAY_NAME_ANONIMO = "Usuario Anónimo"
    PATH_LOGIN = "proyectos/apidocs/get-token"
    PATH_LOGIN_APP = "proyectos/apidocs/get-token-app"
    PATH_CORPUS_PUBLICOS = 'proyectos/apidocs/corpus/'
    PATH_CORPUS_PRIVADOS = 'proyectos/apidocs/corpus/colabora'
    PATH_CORPUS_APP = 'proyectos/apidocs/apps/{app_name}/proyectos'
    PATH_DOCS_CORPUS = 'proyectos/apidocs/corpus/{id_corpus}'
    PATH_DOCS_CORPUS_TABLA = 'proyectos/apidocs/corpus/{id_corpus}/tabla'
    PATH_TAGGED_DOC = 'proyectos/apidocs/corpus/{id_corpus}/{id_doc}/pos'
    PATH_TAGGED_DOC_APP = 'proyectos/apidocs/apps/{id_corpus}/{id_doc}/pos'
    PATH_DOC = 'proyectos/apidocs/corpus/{id_corpus}/{id_doc}'
    PATH_DOC_APP = 'proyectos/apidocs/apps/{id_corpus}/{id_doc}'
    PATH_DOC_META = 'proyectos/apidocs/corpus/{id_corpus}/{id_doc}/meta'
    PATH_DOC_META_APP = 'proyectos/apidocs/apps/{id_corpus}/{id_doc}/meta'
    PATH_CORPUS_META = 'proyectos/apidocs/corpus/{id_corpus}/meta'

    def __init__(self, host,
                 anon_user=None,
                 anon_pass=None,
                 app_name=None,
                 app_password=None):
        self.host = host
        self.token = None
        self.user_info = {}
        self.is_anon_user = None
        self.anon_user = anon_user
        self.anon_pass = anon_pass
        self.app_name = app_name
        self.app_password = app_password
        self.app_token = None
        if self.app_name:
            print(f"Login app {self.app_name}")
            self.login_app()

    def set_user_name(self, name):
        self.user_info["name"] = name

    def is_app_logged(self):
        return self.app_token is not None

    def _get_headers(self):
        headers = {}
        if self.token:
            headers["Authorization"] = "Token " + self.token
        return headers

    def call_endpoint(self, path, method, data=None, headers=None):
        print("Call endpoint " + method + " " + path)
        try:
            url = self.host + path
            print(f"DEBUG URL: {url}")
            if method.lower() == "post":
                resp = requests.post(url ,data=data, headers=headers)
            elif method.lower() == "get":
                resp = requests.get(url, headers=headers)
            if resp.status_code == 401:
                print(resp.text)
                raise Exception("No autorizado: " + resp.text)
            if not resp.ok:
                raise Exception("GECO3 respondió con un error: " + resp.text)
        except Exception as e:
            msg = f"Error en comunicación con GECO3: {e}"
            print(msg)
            raise Exception(f"Error en comunicación con GECO3: {e}")
        return resp

    def login_app(self):
        """ Obtener el token de la aplicación """
        path = self.PATH_LOGIN_APP
        data = {
            'nombre': self.app_name,
            'password': self.app_password,
        }
        resp = self.call_endpoint(path, method="post", data=data)
        self.app_token = resp.json().get("token")

    def get_app_post_data(self):
        return {
            'app': self.app_name,
            'token': self.app_token,
        }

    def login(self, username=None, password=None, token=None, is_token_encrypted=False):
        """ Iniciar sesión con el username y password indicado 
        o bien usar una token determinada. Si no se propociona
        ningún dato se usará el usuario anónimo
        """
        if not token and not username and not password:
            username = self.anon_user
            password = self.anon_pass

        is_anon = username == self.anon_user and not token

        # Caso para token dada
        # Aqui debería checar si la token aun es valida
        # y debería obtener el nombre del usuario
        if token:
            if is_token_encrypted:
                token = token.replace(" ", "+")
                token = decript(self.app_token, token)
            self.token = token
            if not self.init_user(is_anon):
                # token invalida
                print("Token no valida, se intentará obtener otra")
                self.token = None

        if not self.token:
            # de otra manera usar usuario y password dados para obtener una token
            path = self.PATH_LOGIN
            data = {
                'username': username,
                'password': password,
            }
            resp = self.call_endpoint(path, method="post", data=data)
            self.token = resp.json().get("token")
            self.init_user(is_anon)

    def init_user(self, is_anon):
        """ La idea de esto es que se mande llamar un endpoint que nos
        de la informacion del usuario (nombre), y al mismo tiempo
        estaremos confirmando que la token sea válida
        
        Por el momento no hay un endpoint para obtener info del
        usuario así que asumiremos que la token es válida siempre
        (si no lo es lanzaremos una excepción cuando se intente
        acceder a alguno de los otros endpoints)

        Por el momento el nombre del usuario se debe establecer
        aparte usando el método set_user_name()
        """

        name = None
        if is_anon:
            name = self.DISPLAY_NAME_ANONIMO

        self.user_info = {"name": name, "is_anon": is_anon}
        return True

    def corpus_app(self):
        """ Obtiene los corpus disponibles para la aplicación registrada """
        headers = self._get_headers()
        path = self.PATH_CORPUS_APP.format(app_name=self.app_name)
        resp = self.call_endpoint(path, method="get", headers=headers)
        resp = resp.json()
        if "proyectos" in resp:
            return resp["proyectos"]
        return []

    def corpus_publicos(self):
        """ Obtiene todos los corpus publicos """
        headers = self._get_headers()
        path = self.PATH_CORPUS_PUBLICOS
        resp = self.call_endpoint(path, method="get", headers=headers)
        resp = resp.json()
        if "data" in resp:
            corpus = resp["data"]["proyectos"]
            return corpus
        return []

    def corpus_privados(self):
        """ Obtiene los corpus en los que el usuario colabora """
        headers = self._get_headers()
        path = self.PATH_CORPUS_PRIVADOS
        resp = self.call_endpoint(path, method="get", headers=headers)
        resp = resp.json()
        if "data" in resp:
            corpus = resp["data"]["proyectos"]
            return corpus
        return []

    def docs_corpus(self, id_corpus):
        """ Obtiene los documentos del corpus seleccionado """
        headers = self._get_headers()
        path = self.PATH_DOCS_CORPUS.format(id_corpus=id_corpus)
        resp = self.call_endpoint(path, method="get", headers=headers)
        docs = resp.json()["data"]
        return docs

    def docs_tabla(self, id_corpus):
        """ Obtiene todos los documentos del corpus y sus metadatos """
        headers = self._get_headers()
        path = self.PATH_DOCS_CORPUS_TABLA.format(id_corpus=id_corpus)
        resp = self.call_endpoint(path, method="get", headers=headers)
        data = resp.json()["data"]
        metadatos = data["metadatos"]
        tabla = data["tabla"]
        docs = []
        metatados_dict = {}
        for metadato in metadatos:
            metatados_dict[metadato[0]] = metadato[1]
        for id_doc, titulo_doc, metadatos_doc in tabla:
            metadata = {}
            for id_metadato, valor_metadato in metadatos_doc:
                nombre_metadato = metatados_dict[id_metadato]
                metadata[nombre_metadato] = valor_metadato
            doc = {
                "id": id_doc,
                "name": titulo_doc,
                "metadata": metadata
            }
            docs.append(doc)
        return docs

    def _resolve_doc_content_pos_endpoint(self, id_corpus, id_doc):
        if self.app_token:
            path = self.PATH_TAGGED_DOC_APP
            method = "post"
            data = self.get_app_post_data()
        else:
            path = self.PATH_TAGGED_DOC
            method = "get"
            data = None
        path = path.format(id_corpus=id_corpus, id_doc=id_doc)
        return path, method, data

    def doc_content_pos(self, id_corpus, id_doc):
        """ Obtiene el texto con etiquetado POS de un documento"""
        output = []
        headers = self._get_headers()
        path, method, data = self._resolve_doc_content_pos_endpoint(id_corpus, id_doc)
        resp = self.call_endpoint(path, method=method, headers=headers, data=data)
        data = resp.json()["data"]
        for token in data:
            row = (token["token"], token["lemma"], token["tag"], token["prob"])
            row = " ".join(row)
            output.append(row)
            if token["tag"] == "Fp":
                output.append("")
        return "\n".join(output)

    def _resolve_doc_content_endpoint(self, id_corpus, id_doc):
        if self.app_token:
            path = self.PATH_DOC_APP
            method = "post"
            data = self.get_app_post_data()
        else:
            path = self.PATH_DOC
            method = "get"
            data = None
        path = path.format(id_corpus=id_corpus, id_doc=id_doc)
        return path, method, data

    def doc_content(self, id_corpus, id_doc):
        """ Obtiene el texto plano de un documento"""
        headers = self._get_headers()
        path, method, data = self._resolve_doc_content_endpoint(id_corpus, id_doc)
        resp = self.call_endpoint(path, method=method, headers=headers, data=data)
        return resp.json()["data"]

    def metadatos(self, id_corpus):
        headers = self._get_headers()
        path = self.PATH_CORPUS_META.format(id_corpus=id_corpus)
        resp = self.call_endpoint(path, method="get", headers=headers)
        data = resp.json()["data"]
        return data


def xor_cipher_bytes(data: bytes, key: str) -> bytes:
    """
    Realiza una operación XOR entre los bytes del mensaje y los bytes de la clave repetida.

    Parámetros:
    - data: bytes -> mensaje a cifrar o descifrar.
    - key: str -> clave secreta como cadena de texto.

    Retorna:
    - bytes: resultado del cifrado o descifrado en forma de bytes.
    """
    key_bytes: bytes = key.encode('utf-8')
    key_len: int = len(key_bytes)
    result: bytearray = bytearray()
    for i, byte in enumerate(data):
        result.append(byte ^ key_bytes[i % key_len])
    return bytes(result)


def encript(clave: str, mensaje: str) -> str:
    """
    Cifra un mensaje de texto usando XOR y lo convierte a una cadena base64.

    Parámetros:
    - clave: str -> clave secreta para cifrar.
    - mensaje: str -> mensaje original en texto plano.

    Retorna:
    - str: mensaje cifrado codificado como base64.
    """
    mensaje_bytes: bytes = mensaje.encode('utf-8')
    cifrado_bytes: bytes = xor_cipher_bytes(mensaje_bytes, clave)
    cifrado_b64: str = base64.b64encode(cifrado_bytes).decode('utf-8')
    return cifrado_b64


def decript(clave: str, cifrado_b64: str) -> str:
    """
    Descifra un mensaje codificado en base64 que fue cifrado con XOR.

    Parámetros:
    - clave: str -> clave secreta usada en el cifrado.
    - cifrado_b64: str -> mensaje cifrado en formato base64.

    Retorna:
    - str: mensaje original en texto plano (UTF-8).
    """
    cifrado_recibido_bytes: bytes = base64.b64decode(cifrado_b64)
    descifrado_bytes: bytes = xor_cipher_bytes(cifrado_recibido_bytes, clave)
    return descifrado_bytes.decode('utf-8')
