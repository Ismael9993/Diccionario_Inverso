# Diccionario Inverso 

Este proyecto es una plataforma avanzada de análisis semántico y procesamiento de lenguaje natural diseñada para la creación y exploración de **Diccionarios Inversos**. Utiliza el motor de GECO3 para gestionar corpus, procesar textos y visualizar redes de asociaciones semánticas mediante grafos interactivos.

##  Características Principales

*   **Integración con GECO3:** Conexión directa con la API de GECO3 para la gestión de corpus y documentos.
*   **Motor de Diccionario Inverso:** Búsqueda de términos basada en definiciones semánticas utilizando modelos de lenguaje avanzados.
*   **Visualización de Grafos Interactiva:** 
    *   Uso de **Cytoscape.js** para renderizar redes de coocurrencia y asociación.
    *   Sistema de **Aislamiento Visual** para enfocar términos específicos en zonas de alta densidad.
    *   Efectos de animación (pulso y zoom) para localización rápida de nodos.
*   **Gestión de Archivos:** Exportación automática de resultados a formatos estándar como GEXF (grafos), Excel (términos), JSON (normas) y TXT (corpus limpio).
*   **Interfaz Moderna:** Diseño responsivo con soporte para **Modo Oscuro**, arquitectura de cápsulas visuales y navegación intuitiva.

## Tecnologías Utilizadas

*   **Backend:** Python 3.x, Flask, NetworkX, Pandas, SpaCy, NLTK.
*   **Frontend:** JavaScript (Vanilla), Cytoscape.js, Bootstrap 5, CSS3.
*   **Procesamiento:** GECO3 Client, Text2GraphAPI.

## Requisitos Previos

Asegúrate de tener instalado Python 3.8 o superior. Se recomienda el uso de un entorno virtual.

## Instalación

1.  **Clona el repositorio:**
    ```bash
    git clone https://github.com/usuario/diccionario-inverso.git](https://github.com/Ismael9993/Diccionario_Inverso.git
    cd diccionario-inverso
    ```

2.  **Instala las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Descarga el modelo de lenguaje de SpaCy:**
    ```bash
    python -m spacy download es_core_news_lg
    ```

4.  **Configura el archivo `config.json`:**
    Crea un archivo `config.json` en la raíz con el siguiente formato:
    ```json
    {
      "base_url": "http://www.geco.unam.mx/geco3/",
      "anon_user": "anonymous_username",
      "anon_pass": "anonymous_password",
      "app_name": "your_app_name",
      "app_password": "your_app_password",
    }
    ```

## Uso

1.  Inicia el servidor Flask:
    ```bash
    python app.py
    ```
2.  Accede a la aplicación en tu navegador: `http://localhost:5000`
3.  **Flujo de trabajo:**
    *   **Pestaña Inicio:** Información institucional y pedagógica.
    *   **1 Procesar:** En la pestaña Generar nuevo diccionario, selecciona un corpus, elige documentos y genera un nuevo diccionario.
    *   **2 Diccionario/Búsqueda-Grafo:** En la pestaña Diccionarios disponibles, carga un diccionario generado para explorar el grafo e interactuar con sus nodos. Realiza búsquedas inversas introduciendo una definición para encontrar términos relacionados.
    *   **3 Mis Archivos:** Descarga los resultados técnicos del procesamiento.

## Estructura del Proyecto

*   `app.py`: Servidor Flask y endpoints de la API.
*   `Dic_Inv.py`: Motor principal de procesamiento de texto y construcción de grafos.
*   `static/`: Archivos CSS, JavaScript e imágenes.
*   `templates/`: Plantillas HTML (Jinja2).
*   `data/`: Directorio donde se almacenan los diccionarios y grafos generados.⚠️Importante: La carpeta data/ (que contiene los grafos y diccionarios de muestra) no está en este repositorio debido a su peso.Se creará al iniciar el servidor y crear el primer diccionario.
*   `geco3_client/`: Cliente para la comunicación con GECO3.El cliente de GECO3 se encuentra incluido en el repositorio como una carpeta local (geco3_client/). No es necesario instalarlo vía pip, pero asegúrate de que la carpeta esté presente en la raíz del proyecto para que las importaciones funcionen correctamente.


