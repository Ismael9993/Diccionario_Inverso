// ======================
// 1. Estado Global
// ======================
let selectedCorpus = null;
let currentDiccionario = null;
let globalSelectedDocs = new Set();
let currentDocuments = [];
let allDocumentsCache = new Map(); // id -> nombre cache para evitar peticiones redundantes
let lastMetaRes = null;
let lastFilterSelection = {};
let sessionCorpusId = null;
let locationPathName = location.pathname === "/" ? "" : location.pathname;
let monitorInterval = null;
let lastCreatedDic = null; // Guardar el nombre del último diccionario creado

// Selectores UI (accesibles globalmente)
let userDisplay, logoutBtn, corpusListEl, documentsContainer, selectedCorpusInput;
let processBtn, statusText, graphSummary, graphView, definitionInput, searchBtn, resultsList;
let diccionarioSelect, loadDiccionarioBtn, diccionarioStatus, deleteDiccionarioBtn;
let diccionarioSelectFiles, fileListContainer, filesTab;
let progressContainer, progressBar;
let btnFullScreen, btnCenterGraph, btnGraphDark, graphWrapper;
let themeToggle;
let cy = null;
let currentNodeFocus = null;
let graphSearchInput, btnGraphSearch;

document.addEventListener("DOMContentLoaded", function () {
  // Forzar activación de la pestaña de Inicio al cargar la página
  const inicioTab = document.getElementById('inicio-tab');
  if (inicioTab && typeof bootstrap !== 'undefined') {
    const tab = new bootstrap.Tab(inicioTab);
    tab.show();
  }

  // Inicialización de selectores
  userDisplay = document.getElementById("userDisplay");
  logoutBtn = document.getElementById("logoutBtn");
  corpusListEl = document.getElementById("corpusList");
  documentsContainer = document.getElementById("documentsContainer");
  selectedCorpusInput = document.getElementById("selectedCorpus");
  processBtn = document.getElementById("processBtn");
  statusText = document.getElementById("statusText");
  graphSummary = document.getElementById("graphSummary");
  graphView = document.getElementById("graphView");
  definitionInput = document.getElementById("definitionInput");
  searchBtn = document.getElementById("searchBtn");
  resultsList = document.getElementById("resultsList");
  diccionarioSelect = document.getElementById("diccionarioSelect");
  loadDiccionarioBtn = document.getElementById("loadDiccionarioBtn");
  diccionarioStatus = document.getElementById("diccionarioStatus");
  deleteDiccionarioBtn = document.getElementById("deleteDiccionarioBtn");
  diccionarioSelectFiles = document.getElementById("diccionarioSelectFiles");
  fileListContainer = document.getElementById("fileListContainer");
  filesTab = document.getElementById("files-tab");
  progressContainer = document.getElementById("progressContainer");
  progressBar = document.getElementById("progressBar");
  btnFullScreen = document.getElementById("btnFullScreen");
  btnCenterGraph = document.getElementById("btnCenterGraph");
  btnGraphDark = document.getElementById("btnGraphDark");
  graphWrapper = document.getElementById("graphWrapper");
  themeToggle = document.getElementById("themeToggle");

  // --- LÓGICA DE MODO OSCURO (PERSISTENCIA) ---
  const currentTheme = localStorage.getItem("theme") || "light";
  document.documentElement.setAttribute("data-theme", currentTheme);
  updateThemeIcon(currentTheme);

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      let theme = document.documentElement.getAttribute("data-theme");
      theme = theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", theme);
      localStorage.setItem("theme", theme);
      updateThemeIcon(theme);
    });
  }

  function updateThemeIcon(theme) {
    if (!themeToggle) return;
    const icon = themeToggle.querySelector("i");
    if (theme === "dark") {
      icon.className = "bi bi-sun fs-5";
    } else {
      icon.className = "bi bi-moon-stars fs-5";
    }
  }

  // ======================
  // 2. Funciones API
  // ======================

  function checkAuthStatus() {
    fetch(locationPathName + "/api/auth/status")
      .then(r => r.json())
      .then(res => {
        if (res.ok && res.authenticated) {
          userDisplay.innerHTML = `<i class="bi bi-person-circle me-1"></i>${res.name || 'Usuario autenticado'}`;
          logoutBtn.style.display = "inline-block";
          if (res.corpus) sessionCorpusId = parseInt(res.corpus);
        } else {
          userDisplay.innerHTML = `<i class="bi bi-person-circle me-1"></i>Usuario Anónimo`;
          logoutBtn.style.display = "none";
        }
      })
      .catch(err => {
        console.error("Error comprobando autenticación:", err);
        userDisplay.innerHTML = `<i class="bi bi-person-circle me-1"></i>Usuario Anónimo`;
        logoutBtn.style.display = "none";
      })
      .finally(() => {
        loadCorpora();
      });
  }

  function loadCorpora() {
    fetch(locationPathName + "/api/corpora")
      .then(r => r.json())
      .then(res => {
        if (res.ok) {
          res.data.forEach(c => {
            const li = document.createElement("li");
            li.className = "list-group-item";
            li.innerText = c.nombre;
            li.dataset.id = c.id;

            li.addEventListener("click", function () {
              document.querySelectorAll("#corpusList .list-group-item").forEach(x => x.classList.remove("active"));
              this.classList.add("active");

              selectedCorpus = { id: c.id, nombre: c.nombre };
              selectedCorpusInput.value = c.nombre;
              selectedCorpusInput.dataset.corpusId = c.id;

              globalSelectedDocs.clear();
              lastFilterSelection = {};
              allDocumentsCache.clear();

              fetchDocumentsAndMeta(c.id);
            });

            corpusListEl.appendChild(li);
          });

          if (sessionCorpusId) {
            const matchingItem = corpusListEl.querySelector(`[data-id="${sessionCorpusId}"]`);
            if (matchingItem) matchingItem.click();
          }
        } else {
          corpusListEl.innerHTML = `<li class='list-group-item text-danger'>Error cargando corpora: ${res.error || 'Desconocido'}</li>`;
          if (statusBox) statusBox.innerText = `Error cargando corpora: ${res.error}`;
        }
      })
      .catch(err => {
        console.error(err);
        corpusListEl.innerHTML = `<li class='list-group-item text-danger'>Error de red al cargar corpora</li>`;
      });
  }

  async function fetchDocumentsAndMeta(corpusId) {
    documentsContainer.innerHTML = "<p class='text-muted'>Cargando documentos y metadatos...</p>";
    try {
      const [metaRes, docsRes] = await Promise.all([
        fetch(locationPathName + `/api/metadatos/${corpusId}`).then(r => r.json()),
        fetch(locationPathName + `/api/documentos/${corpusId}`).then(r => r.json())
      ]);

      if (!metaRes.ok) throw new Error(metaRes.error || "Error cargando metadatos");
      if (!docsRes.ok) throw new Error(docsRes.error || "Error cargando documentos");

      lastMetaRes = metaRes;
      currentDocuments = docsRes.data;

      currentDocuments.forEach(d => allDocumentsCache.set(d.id, d.archivo));

      displayDocuments(currentDocuments, corpusId, lastMetaRes);
    } catch (error) {
      documentsContainer.innerHTML = `<p class="text-danger">${error.message}</p>`;
      if (statusText) statusText.innerText = `Error: ${error.message}`;
    }
  }

  async function fetchFilteredDocuments(corpusId, metas, valores) {
    documentsContainer.innerHTML = "<p class='text-muted'>Aplicando filtros...</p>";
    try {
      const url = locationPathName + `/api/documentos/${corpusId}?meta=${encodeURIComponent(metas.join(","))}&valor=${encodeURIComponent(valores.join(","))}`;
      const res = await fetch(url).then(r => r.json());
      if (!res.ok) throw new Error(res.error || "Error al filtrar documentos");

      currentDocuments = res.data;
      currentDocuments.forEach(d => allDocumentsCache.set(d.id, d.archivo));

      displayDocuments(currentDocuments, corpusId, lastMetaRes);
    } catch (error) {
      documentsContainer.innerHTML = `<p class='text-danger'>${error.message}</p>`;
      if (statusText) statusText.innerText = `Error: ${error.message}`;
    }
  }

  // Función pura para pintar HTML
  function displayDocuments(docs, corpusId, metaRes) {
    let metaPanel = "";
    if (metaRes && metaRes.ok && metaRes.data.length > 0) {
      metaPanel = `
            <div class="mb-2 p-2 border rounded bg-light">
                <label class="form-label small mb-1"><b>Filtrar por metadatos:</b></label>
                <div id="multiMetaPanel" class="mb-2">
                    ${metaRes.data.map((m, i) => {
        const selectedVal = lastFilterSelection[m.nombre] || "";
        return `
                        <div class="input-group input-group-sm mb-2">
                            <span class="input-group-text">${m.nombre}</span>
                            <select class="form-select meta-filter-select" data-meta="${m.nombre}">
                                <option value="">--Cualquiera--</option>
                                ${m.valores.map(v => `<option value="${v}" ${selectedVal === v ? "selected" : ""}>${v}</option>`).join("")}
                            </select>
                        </div>`;
      }).join("")}
                </div>
            </div>`;
    }

    let html = metaPanel;

    html += `<div id="selectedDocsAlertContainer"></div>`;

    if (docs.length === 0) {
      documentsContainer.innerHTML = html + "<p class='text-muted'>No hay documentos.</p>";
      updateSelectedDocsAlert();
      return;
    }

    html += `
        <div class='mb-2'>
            <button id='selectAllDocs' class='btn btn-sm btn-outline-secondary'>Seleccionar visibles</button>
            <button id='clearAllDocs' class='btn btn-sm btn-outline-secondary'>Deseleccionar visibles</button>
        </div>`;

    const listHtml = docs.map(doc => {
      const checked = globalSelectedDocs.has(doc.id) ? "checked" : "";
      return `
            <div class="form-check">
                <input class="form-check-input doc-check" type="checkbox" value="${doc.id}" id="doc_${doc.id}" ${checked}>
                <label class="form-check-label" for="doc_${doc.id}">${doc.archivo}</label>
            </div>`;
    }).join("");

    documentsContainer.innerHTML = html + `<div>${listHtml}</div>`;

    updateSelectedDocsAlert();

    // Event listeners locales a los documentos pintados
    document.getElementById("selectAllDocs")?.addEventListener("click", () => {
      document.querySelectorAll(".doc-check").forEach(cb => {
        cb.checked = true;
        globalSelectedDocs.add(parseInt(cb.value));
      });
      updateSelectedDocsAlert();
    });

    document.getElementById("clearAllDocs")?.addEventListener("click", () => {
      document.querySelectorAll(".doc-check").forEach(cb => {
        cb.checked = false;
        globalSelectedDocs.delete(parseInt(cb.value));
      });
      updateSelectedDocsAlert();
    });

    document.querySelectorAll(".doc-check").forEach(cb => {
      cb.addEventListener("change", () => {
        const id = parseInt(cb.value);
        if (cb.checked) globalSelectedDocs.add(id);
        else globalSelectedDocs.delete(id);
        updateSelectedDocsAlert();
      });
    });
  }

  function updateSelectedDocsAlert() {
    const container = document.getElementById("selectedDocsAlertContainer");
    if (!container) return;

    if (globalSelectedDocs.size === 0) {
      container.innerHTML = "";
      return;
    }

    const selectedDocsInfo = Array.from(globalSelectedDocs).map(id => {
      return allDocumentsCache.get(id) || `ID: ${id}`;
    }).join(", ");

    container.innerHTML = `
        <div class='alert alert-info mb-3 selected-docs-alert'>
            <strong> Documentos seleccionados (${globalSelectedDocs.size}):</strong>
            <div class='small mt-1' style='max-height: 100px; overflow-y: auto;'>${selectedDocsInfo}</div>
        </div>`;
  }

  function monitorearProgreso() {
    if (monitorInterval) clearInterval(monitorInterval);

    monitorInterval = setInterval(() => {
      fetch(locationPathName + "/api/status")
        .then(r => r.json())
        .then(res => {
          if (res.status === "processing") {
            statusBox.innerText = "⏳ " + res.message;
          } else if (res.status === "done" || res.status === "error") {
            clearInterval(monitorInterval);
            if (res.status === "done") {
              statusBox.innerText = "✅ Finalizado: " + res.message;
            } else {
              statusBox.innerText = "❌ Error: " + res.message;
            }
          }
        })
        .catch(err => {
          clearInterval(monitorInterval);
          console.error("Error monitoreando progreso:", err);
          statusBox.innerText = "❌ Error de conexión al monitorear";
        });
    }, 2000);
  }

  async function loadDiccionarios() {
    try {
      // Añadimos un timestamp para evitar cache del navegador
      const res = await fetch(locationPathName + "/api/diccionarios?t=" + new Date().getTime()).then(r => r.json());
      console.log("Respuesta de /api/diccionarios:", res);
      
      if (res.ok && res.data) {
        // Limpiar y rellenar el select de diccionarios
        if (diccionarioSelect) {
          diccionarioSelect.innerHTML = '<option value="">Selecciona un diccionario...</option>';
          res.data.forEach(dic => {
            const opt = document.createElement("option");
            opt.value = dic.nombre;
            opt.textContent = `${dic.nombre} (${dic.n_nodos} nodos)`;
            diccionarioSelect.appendChild(opt);
          });

          if (currentDiccionario) {
            diccionarioSelect.value = currentDiccionario;
          }
        }
        return res.data; // Retornamos los datos para validación
      } else {
        if (diccionarioSelect) {
          diccionarioSelect.innerHTML = "<option value=''>No hay diccionarios guardados</option>";
        }
        return [];
      }
    } catch (err) {
      console.error("Error cargando diccionarios", err);
      if (diccionarioSelect) {
        diccionarioSelect.innerHTML = "<option value=''>Error cargando diccionarios</option>";
      }
      return [];
    }
  }

  function renderGraphPreview(graphJson) {
    graphView.innerHTML = "";
    graphView.style.opacity = "0";

    const loader = document.getElementById('graphLoader');
    if (loader) {
      loader.classList.remove('d-none');
      loader.classList.add('d-flex');
    }

    // Configurar Summary y Slider
    const summarySpan = document.getElementById("graphSummary").querySelector("span");
    if (summarySpan) {
      summarySpan.innerHTML = `<strong>Nodos:</strong> ${graphJson.nodes.length} | <strong>Aristas:</strong> ${graphJson.edges.length}`;
    }

    let maxWeight = 0;
    if (graphJson.edges && graphJson.edges.length > 0) {
      maxWeight = Math.max(...graphJson.edges.map(e => e.weight));
    }
    const filterInput = document.getElementById("edgeFilter");
    if (filterInput) {
      filterInput.max = Math.max(maxWeight, 2);
      filterInput.value = 2;
    }

    // Preparar elementos cytoscape
    const elements = [
      ...graphJson.nodes.map(n => ({ data: { id: n.id, frequency: n.frequency, degree: n.degree } })),
      ...graphJson.edges.map(e => ({ data: { source: e.source, target: e.target, weight: e.weight } }))
    ];

    cy = cytoscape({
      container: graphView,
      elements: elements,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(id)',
            'width': 'mapData(frequency, 0, 100, 20, 60)',
            'height': 'mapData(frequency, 0, 100, 20, 60)',
            'background-color': 'mapData(degree, 0, 50, #0d6efd, #ffc107)',
            'color': document.documentElement.getAttribute('data-theme') === 'dark' ? '#e0e0e0' : '#333',
            'font-size': '12px',
            'font-family': "'JetBrains Mono', monospace",
            'text-valign': 'top',
            'text-margin-y': -5
          }
        },
        {
          selector: 'edge',
          style: {
            'width': 'mapData(weight, 0, 10, 1, 5)',
            'line-color': document.documentElement.getAttribute('data-theme') === 'dark' ? '#555' : '#ccc',
            'opacity': 0.6
          }
        },
        {
          selector: '.elements-faded',
          style: {
            'opacity': 0.1
          }
        },
        {
          selector: '.element-highlight',
          style: {
            'opacity': 1,
            'z-index': 999
          }
        }
      ],
      layout: {
        name: 'cose',
        animate: false,           // Sin animaciones intermedias para ganar velocidad
        fit: true,
        padding: 40,
        // --- Optimización de Repulsión y Espaciado ---
        nodeRepulsion: 12000,     // Aumentado para que los nodos se separen más
        idealEdgeLength: 120,     // Longitud ideal de las aristas
        edgeElasticity: 100,
        componentSpacing: 150,    // Espacio entre componentes desconectados
        // --- Control de Tiempo y Rendimiento ---
        numIter: 1200,            // Límite máximo de iteraciones
        coolingFactor: 0.85,      // Enfriamiento más rápido (menor número = más rápido se detiene)
        initialTemp: 300,         // Temperatura inicial
        randomize: true           // Ayuda a que los nodos no partan todos del mismo punto
      }
    });

    cy.one('layoutstop', function () {
      const loader = document.getElementById('graphLoader');
      if (loader) {
        loader.classList.remove('d-flex');
        loader.classList.add('d-none');
        // Eliminamos posible estilo de display manual
        loader.style.display = 'none';
      }
      if (graphView) {
        graphView.style.opacity = '1';
        cy.fit(); // Ajustar el grafo al contenedor
      }
      console.log("Layout finalizado exitosamente.");
    });

    // PLAN B: Seguro de emergencia (6 segundos)
    setTimeout(() => {
      const loader = document.getElementById('graphLoader');
      // Usamos includes('d-flex') o verificamos si aún está visible
      if (loader && !loader.classList.contains('d-none')) {
        console.warn("Layout excedió el tiempo límite. Forzando visualización...");
        if (cy && cy.stop) cy.stop(); // Detener cálculos pesados
        loader.classList.remove('d-flex');
        loader.classList.add('d-none');
        loader.style.display = 'none';
        if (graphView) {
          graphView.style.opacity = '1';
          cy.animate({ fit: { padding: 40 } }, { duration: 500 });
        }
      }
    }, 6000);

    // Aplicar el filtro inicial inmediatamente
    if (filterInput && filterInput.value > 0) {
      const val = parseFloat(filterInput.value);
      cy.edges().forEach(edge => {
        if (edge.data('weight') < val) {
          edge.style('display', 'none');
        }
      });
    }

    // Panel interactivo de Nodo
    cy.on('tap', 'node', function (evt) {
      const node = evt.target;
      cy.elements().removeClass('elements-faded').removeClass('element-highlight');
      showNodeDetails(node.id(), node);
    });

    // Limpiar fade al hacer clic en el fondo
    cy.on('tap', function (evt) {
      if (evt.target === cy) {
        cy.elements().removeClass('elements-faded').removeClass('element-highlight');
      }
    });
  }

  function showNodeDetails(nodeId, nodeObj) {
    currentNodeFocus = nodeObj; // Guardar referencia global

    document.getElementById("nodeDetailsTitle").innerText = nodeId;
    document.getElementById("nodeDetailsDef").innerText = "Buscando definición...";
    document.getElementById("nodeDetailsFreq").innerText = nodeObj.data('frequency') || "0";
    document.getElementById("nodeDetailsDegree").innerText = nodeObj.data('degree') || "0";

    const neighborsList = document.getElementById("nodeDetailsNeighbors");
    neighborsList.innerHTML = "";

    // Abrir el panel Offcanvas usando Bootstrap
    const panelEl = document.getElementById("nodeDetailsPanel");
    const offcanvas = bootstrap.Offcanvas.getInstance(panelEl) || new bootstrap.Offcanvas(panelEl);
    offcanvas.show();

    // Extraer aristas conectadas, ordenarlas por peso
    const connectedEdges = nodeObj.connectedEdges().sort((a, b) => b.data('weight') - a.data('weight'));
    const topEdges = connectedEdges.slice(0, 10);

    topEdges.forEach(edge => {
      // Determinar cuál es el nodo vecino en esta arista
      const neighbor = edge.source().id() === nodeId ? edge.target() : edge.source();
      const weight = edge.data('weight');

      const li = document.createElement("li");
      li.className = "list-group-item d-flex justify-content-between align-items-center px-2 bg-transparent";
      li.innerHTML = `
        <span class="text-truncate"><i class="bi bi-link-45deg me-2 text-muted"></i>${neighbor.id()}</span>
        <span class="badge bg-secondary rounded-pill" title="Peso de la conexión">${weight.toFixed(2)}</span>
      `;
      neighborsList.appendChild(li);
    });

    if (topEdges.length === 0) {
      neighborsList.innerHTML = "<li class='list-group-item text-muted bg-transparent px-2'>Sin vecinos conectados.</li>";
    }

    // Pedir info del nodo
    const currentDiccionario = diccionarioSelect.value;
    fetch(locationPathName + "/api/node_info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ node_id: nodeId, diccionario: currentDiccionario })
    })
      .then(r => r.json())
      .then(res => {
        if (res.ok) {
          document.getElementById("nodeDetailsDef").innerText = res.definicion;
        } else {
          document.getElementById("nodeDetailsDef").innerText = "Sin definición exacta.";
        }
      })
      .catch(() => {
        document.getElementById("nodeDetailsDef").innerText = "Error cargando datos.";
      });
  }

  // ======================
  // 3. Event Listeners
  // ======================

  documentsContainer.addEventListener("change", e => {
    if (!e.target.matches(".meta-filter-select")) return;

    const corpusId = selectedCorpus?.id;
    if (!corpusId) return;

    const selects = document.querySelectorAll(".meta-filter-select");
    const metas = [];
    const valores = [];
    lastFilterSelection = {};

    selects.forEach(sel => {
      if (sel.value) {
        metas.push(sel.dataset.meta);
        valores.push(sel.value);
        lastFilterSelection[sel.dataset.meta] = sel.value;
      }
    });

    if (metas.length === 0) {
      fetchDocumentsAndMeta(corpusId);
    } else {
      fetchFilteredDocuments(corpusId, metas, valores);
    }
  });

  processBtn.addEventListener("click", function () {
    const corpusId = selectedCorpusInput.dataset.corpusId;
    if (!corpusId) {
      alert("Selecciona un corpus primero.");
      return;
    }

    const docIds = Array.from(globalSelectedDocs);
    if (docIds.length === 0) {
      alert("Selecciona al menos un documento.");
      return;
    }

    const dicName = prompt("Nombre del nuevo diccionario:", "Mi_Diccionario");
    if (!dicName) return;
    lastCreatedDic = dicName; // Guardamos para la carga automática
    selectedCorpusInput.value = dicName; // Visual en el input
    // UI: Preparar el estado visual
    statusText.textContent = "Iniciando proceso en el servidor...";
    statusText.className = "small fw-bold text-secondary"; // Clase para animación
    processBtn.disabled = true;

    if (progressContainer && progressBar) {
      progressContainer.style.display = "flex";
      progressBar.style.width = "0%";
      progressBar.innerText = "0%";
      progressBar.className = "progress-bar progress-bar-striped progress-bar-animated bg-primary";
    }

    fetch(locationPathName + "/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corpus_id: parseInt(corpusId),
        doc_ids: docIds,
        dic_name: dicName
      })
    })
      .then(r => r.json())
      .then(res => {
        if (res.ok) {
          // ✅ Iniciamos el monitoreo constante cada segundo
          iniciarMonitoreo();
        } else {
          statusText.textContent = "Error: " + res.error;
          statusText.className = "small fw-bold text-danger";
          processBtn.disabled = false;
        }
      })
      .catch(err => {
        statusText.textContent = "Error de conexión con el servidor.";
        statusText.className = "small fw-bold text-danger";
        processBtn.disabled = false;
      });
  });

  // --- FUNCIÓN DE MONITOREO REFORZADA ---
  // --- FUNCIÓN DE MONITOREO REFORZADA CON AUTO-CARGA ---
  function iniciarMonitoreo() {
    if (monitorInterval) clearInterval(monitorInterval);

    monitorInterval = setInterval(() => {
      fetch(locationPathName + "/api/status")
        .then(r => r.json())
        .then(async (res) => { // Mantenemos async para el uso de await
          statusText.textContent = res.message || "Procesando...";
          statusText.className = "small fw-bold text-secondary";

          if (progressBar) {
            let pct = 0;
            const msg = res.message || "";
            if (msg.includes("Fase 1")) pct = 20;
            else if (msg.includes("Fase 2")) pct = 45;
            else if (msg.includes("Fase 3")) pct = 70;
            else if (msg.includes("Fase 4")) pct = 90;

            if (pct > 0) {
              progressBar.style.width = pct + "%";
              progressBar.innerText = pct + "%";
            }
          }

          if (res.status === "done") {
            clearInterval(monitorInterval);
            statusText.textContent = "✅ " + (res.message || "Proceso completado.");
            statusText.className = "small fw-bold text-success";
            processBtn.disabled = false;

            if (progressBar) {
              progressBar.style.width = "100%";
              progressBar.innerText = "100%";
              progressBar.className = "progress-bar bg-success";
            }

            // --- LÓGICA DE AUTO-CARGA REFORZADA CON RETRASO DE SEGURIDAD ---
            const nombreUsuario = lastCreatedDic || "";
            const nombreNormalizado = nombreUsuario.replace(/ /g, "_");
            console.log("Proceso finalizado. Iniciando auto-carga para:", nombreUsuario, "(Norm:", nombreNormalizado, ")");

            setTimeout(async () => {
              // 1. Refrescar el select del HTML (asegura que el índice esté cargado)
              const listaDics = await loadDiccionarios();
              console.log("Lista actualizada recibida:", listaDics);

              // 2. Forzar la selección del nuevo diccionario en el menú
              if (diccionarioSelect) {
                // Intentamos seleccionar por nombre normalizado (preferido en el backend) o original
                diccionarioSelect.value = nombreNormalizado;
                if (!diccionarioSelect.value) diccionarioSelect.value = nombreUsuario;
                
                if (!diccionarioSelect.value) {
                    console.warn("No se pudo seleccionar automáticamente en el dropdown. Intentando carga forzada.");
                }
              }

              const finalName = (diccionarioSelect && diccionarioSelect.value) ? diccionarioSelect.value : nombreNormalizado;

              if (finalName) {
                console.log("Cargando diccionario final:", finalName);
                // 3. Cargar los datos del grafo directamente
                cargarDiccionario(finalName);

                // 4. Cambiamos a la pestaña de Diccionarios (Grafo) usando la API de Bootstrap
                const graphTabEl = document.getElementById("tab2-tab");
                if (graphTabEl) {
                  const tab = bootstrap.Tab.getOrCreateInstance(graphTabEl);
                  tab.show();
                }
              }
              console.log("¡Intento de auto-carga completado!");
            }, 1000); // Aumentamos a 1s por seguridad extra

          } else if (res.status === "error") {
            clearInterval(monitorInterval);
            statusText.textContent = "❌ " + (res.message || "Error en el proceso.");
            statusText.className = "small fw-bold text-danger";
            processBtn.disabled = false;

            if (progressBar) {
              progressBar.style.width = "100%";
              progressBar.innerText = "Error";
              progressBar.className = "progress-bar bg-danger";
            }
          }
        })
        .catch(err => {
          console.error("Error de monitoreo:", err);
          clearInterval(monitorInterval);
        });
    }, 1000);
  }




  loadDiccionarioBtn.addEventListener("click", () => {
    const nombre = diccionarioSelect.value;
    cargarDiccionario(nombre);
  });

  async function cargarDiccionario(nombre) {
    if (!nombre) {
      alert("Selecciona un diccionario.");
      return;
    }

    // Normalización preventiva para el selector
    const nombreNormalizado = nombre.trim();

    // Sincronizar el selector visual si es necesario
    if (diccionarioSelect.value !== nombre) {
      diccionarioSelect.value = nombre;
    }

    // Guardar preferencia
    localStorage.setItem("lastDiccionario", nombre);
    diccionarioStatus.innerText = "Cargando...";

    try {
      const res = await fetch(locationPathName + "/api/load_diccionario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre })
      }).then(r => r.json());

      if (res.ok) {
        diccionarioStatus.innerText = res.message;
        currentDiccionario = nombre;
        graphSummary.innerHTML = `<strong>Nodos:</strong> ${res.graph.nodes.length} — <strong>Aristas:</strong> ${res.graph.edges.length}`;
        renderGraphPreview(res.graph);
      } else {
        diccionarioStatus.innerText = "Error: " + res.error;
        if (statusBox) statusBox.innerText = "Error: " + res.error;
      }
    } catch (err) {
      diccionarioStatus.innerText = "Error de red al cargar.";
      console.error(err);
    }
  }

  deleteDiccionarioBtn.addEventListener("click", async () => {
    const nombre = diccionarioSelect.value;
    if (!nombre) {
      alert("Por favor, selecciona un diccionario de la lista para eliminar.");
      return;
    }

    if (!confirm(`¿Estás seguro de que quieres eliminar el diccionario "${nombre}"?\n\nSi no eres el creador, la acción fallará.`)) {
      return;
    }

    deleteDiccionarioBtn.disabled = true;

    try {
      const res = await fetch(locationPathName + "/api/delete_diccionario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre: nombre })
      }).then(r => r.json());

      if (res.ok) {
        alert(res.message);
        loadDiccionarios();
        document.getElementById("graphView").innerHTML = `
          <div class="text-center" id="graphEmptyState">
              <i class="bi bi-diagram-3" style="font-size: 3rem; opacity: 0.3;"></i>
              <p class="mt-2 mb-0">Selecciona un diccionario para visualizar el grafo</p>
          </div>
        `;
        document.getElementById("graphSummary").innerHTML = "Diccionario eliminado.";
        document.getElementById("diccionarioStatus").innerText = "Ninguno cargado";
      } else {
        alert("Error: " + res.error);
        if (statusBox) statusBox.innerText = "Error eliminando: " + res.error;
      }
    } catch (error) {
      alert("Error de conexión al intentar borrar.");
      console.error(error);
    } finally {
      deleteDiccionarioBtn.disabled = false;
    }
  });

  searchBtn.addEventListener("click", function () {
    const def = definitionInput.value.trim();
    if (!def) {
      alert("Introduce una definición.");
      return;
    }

    if (!currentDiccionario) {
      alert("Selecciona o carga un diccionario.");
      return;
    }

    resultsList.innerHTML = "<li>Cargando...</li>";

    fetch(locationPathName + "/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        definition: def,
        top_k: 20,
        diccionario: currentDiccionario
      })
    })
      .then(r => r.json())
      .then(res => {
        if (res.ok) {
          resultsList.innerHTML = "";
          res.results.forEach(r => {
            const li = document.createElement("li");
            li.className = "search-result-item";
            li.innerHTML = `<span class="data-font fw-bold">${r.palabra.replace(/_/g, " ")}</span>`;
            resultsList.appendChild(li);
          });
        } else {
          resultsList.innerHTML = `<li class="text-danger">${res.error}</li>`;
        }
      })
      .catch(err => {
        resultsList.innerHTML = `<li class="text-danger">Error de red</li>`;
        console.error(err);
      });
  });

  document.getElementById("tab2-tab")?.addEventListener("click", function () {
    loadDiccionarios();
    // Forzar redibujado de Cytoscape si se renderizó mientras la pestaña estaba oculta
    if (typeof cy !== 'undefined' && cy) {
      setTimeout(() => {
        cy.resize();
        cy.fit();
      }, 100);
    }
  });

  // --- LÓGICA DE MIS DOCUMENTOS ---
  async function loadDiccionariosFiles() {
    try {
      const res = await fetch(locationPathName + "/api/diccionarios").then(r => r.json());
      if (res.ok && res.data && res.data.length > 0) {
        diccionarioSelectFiles.innerHTML = '<option value="">-- Selecciona un diccionario --</option>' + res.data
          .map(d => `<option value="${d.nombre}">${d.nombre}</option>`)
          .join("");
      } else {
        diccionarioSelectFiles.innerHTML = "<option value=''>No hay diccionarios guardados</option>";
      }
    } catch (err) {
      console.error("Error cargando diccionarios para archivos", err);
      diccionarioSelectFiles.innerHTML = "<option value=''>Error cargando diccionarios</option>";
    }
  }

  if (filesTab) {
    filesTab.addEventListener("click", () => {
      loadDiccionariosFiles();
      fileListContainer.innerHTML = '<p class="text-muted text-center p-4">Selecciona un diccionario para ver los archivos disponibles.</p>';
    });
  }

  if (diccionarioSelectFiles) {
    diccionarioSelectFiles.addEventListener("change", (e) => {
      const dicName = e.target.value;
      if (!dicName) {
        fileListContainer.innerHTML = '<p class="text-muted text-center p-4">Selecciona un diccionario para ver los archivos disponibles.</p>';
        return;
      }
      renderFileLinks(dicName);
    });
  }

  function renderFileLinks(dicName) {
    const files = [
      { name: "grafo_ventana10.gexf", title: "Grafo de Coocurrencias", type: "grafo", icon: "bi-diagram-3-fill" },
      { name: "grafo_asociacion.gexf", title: "Grafo Galex Asociación", type: "grafo", icon: "bi-diagram-3-fill" },
      { name: "grafo_frecuencia.gexf", title: "Grafo Galex Frecuencia", type: "grafo", icon: "bi-diagram-3-fill" },
      { name: "terminos_definiciones.xlsx", title: "Excel de Términos", type: "excel", icon: "bi-file-earmark-excel-fill" },
      { name: "corpus_completo_lematizado_limpio.txt", title: "Corpus Lematizado", type: "text", icon: "bi-file-earmark-text-fill" },
      { name: "normas_asociacion.json", title: "Normas de Asociación", type: "json", icon: "bi-filetype-json" }
    ];

    fileListContainer.innerHTML = "";

    files.forEach(file => {
      let borderClass = "";
      let iconColorClass = "";

      if (file.type === "grafo") {
        borderClass = "border-grafo";
        iconColorClass = "text-primary";
      } else if (file.type === "excel") {
        borderClass = "border-excel";
        iconColorClass = "text-success";
      } else if (file.type === "text") {
        borderClass = "border-text";
        iconColorClass = "text-secondary";
      } else if (file.type === "json") {
        borderClass = "border-json";
        iconColorClass = "text-warning";
      }

      const col = document.createElement("div");
      col.className = "col-md-4 col-sm-6";

      const card = document.createElement("div");
      card.className = `file-card ${borderClass}`;

      const fileInfo = document.createElement("div");
      fileInfo.className = "mb-3";
      fileInfo.innerHTML = `
        <div class="d-flex align-items-center mb-2">
            <i class="bi ${file.icon} fs-4 me-2 ${iconColorClass}"></i> 
            <span class="file-title mb-0">${file.title}</span>
        </div>
        <div class="file-name data-font">${file.name}</div>
      `;

      const btn = document.createElement("a");
      btn.href = `${locationPathName}/api/descargar/${encodeURIComponent(dicName)}/${encodeURIComponent(file.name)}`;
      btn.className = "btn btn-outline-dark btn-sm w-100 file-download-btn";
      btn.target = "_blank";
      btn.innerHTML = '<i class="bi bi-download me-1"></i> Descargar';

      card.appendChild(fileInfo);
      card.appendChild(btn);
      col.appendChild(card);
      fileListContainer.appendChild(col);
    });
  }

  // --- LÓGICA DE HERRAMIENTAS DEL GRAFO ---
  if (btnFullScreen && graphWrapper) {
    btnFullScreen.addEventListener("click", () => {
      graphWrapper.classList.toggle("graph-fullscreen");

      const icon = btnFullScreen.querySelector("i");
      if (icon) {
        if (graphWrapper.classList.contains("graph-fullscreen")) {
          icon.classList.remove("bi-arrows-fullscreen");
          icon.classList.add("bi-fullscreen-exit");
        } else {
          icon.classList.remove("bi-fullscreen-exit");
          icon.classList.add("bi-arrows-fullscreen");
        }
      }

      // Ajustar ancho del panel offcanvas
      const panelEl = document.getElementById("nodeDetailsPanel");
      if (panelEl) {
        if (graphWrapper.classList.contains("graph-fullscreen")) {
          panelEl.style.width = "350px";
        } else {
          panelEl.style.width = "";
        }
      }

      // Redimensionar si se está usando cytoscape
      if (typeof cy !== 'undefined' && cy.resize) {
        cy.resize();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && graphWrapper.classList.contains("graph-fullscreen")) {
        btnFullScreen.click();
      }
    });
  }

  if (btnCenterGraph) {
    btnCenterGraph.addEventListener("click", () => {
      // Intentar centrar según la librería que esté en uso globalmente
      if (typeof cy !== 'undefined' && cy.fit) {
        cy.fit();
      } else if (typeof s !== 'undefined' && s.cameras) {
        // En caso de usar Sigma.js
        s.cameras[0].goTo({ x: 0, y: 0, ratio: 1 });
      }
    });
  }

  if (btnGraphDark && graphWrapper) {
    btnGraphDark.addEventListener("click", () => {
      graphWrapper.classList.toggle("graph-dark-mode");
      const isDark = graphWrapper.classList.contains("graph-dark-mode");

      const icon = btnGraphDark.querySelector("i");
      if (icon) {
        if (isDark) {
          icon.classList.remove("bi-moon-stars");
          icon.classList.add("bi-sun");
        } else {
          icon.classList.remove("bi-sun");
          icon.classList.add("bi-moon-stars");
        }
      }

      // Actualizar colores del grafo Cytoscape
      if (cy) {
        cy.style()
          .selector('node')
          .style('color', isDark ? '#e0e0e0' : '#333')
          .selector('edge')
          .style('line-color', isDark ? '#555' : '#ccc')
          .update();
      }
    });
  }

  // Bind filter
  const edgeFilter = document.getElementById("edgeFilter");
  if (edgeFilter) {
    edgeFilter.addEventListener("input", (e) => {
      if (!cy) return;
      const val = parseFloat(e.target.value);
      cy.edges().forEach(edge => {
        if (edge.data('weight') < val) {
          edge.style('display', 'none');
        } else {
          edge.style('display', 'element');
        }
      });
    });
  }

  // --- LÓGICA DE CENTRADO DE NODO ---
  const btnFocusNode = document.getElementById("btnFocusNode");
  if (btnFocusNode) {
    btnFocusNode.addEventListener("click", () => {
      if (cy && currentNodeFocus) {
        // Ejecutar aislamiento visual antes de centrar
        aplicarModoAislamiento(currentNodeFocus.id());

        cy.animate({
          center: { eles: currentNodeFocus },
          zoom: 3.5 // Zoom aumentado para ver términos pequeños
        }, { duration: 500 });

        // Efecto de pulso: el nodo crece y cambia a rojo brillante
        const originalWidth = currentNodeFocus.style('width');
        const originalColor = currentNodeFocus.style('background-color');

        currentNodeFocus.animate({
          style: {
            'background-color': '#ff0000',
            'width': '80px',
            'height': '80px'
          }
        }, { duration: 400 }).delay(200).animate({
          style: {
            'background-color': originalColor,
            'width': originalWidth,
            'height': originalWidth
          }
        }, { duration: 400 });

        // Cerrar el offcanvas opcionalmente para despejar la vista
        // const panelEl = document.getElementById("nodeDetailsPanel");
        // const offcanvas = bootstrap.Offcanvas.getInstance(panelEl);
        // if (offcanvas) offcanvas.hide();
      }
    });
  }

  // --- LÓGICA DE BÚSQUEDA EN EL GRAFO ---
  graphSearchInput = document.getElementById("graphSearchInput");
  btnGraphSearch = document.getElementById("btnGraphSearch");

  // Aísla el nodo seleccionado y sus vecinos directos, opacando el resto
  function aplicarModoAislamiento(nodoId) {
    if (!cy) return;
    const targetNode = cy.getElementById(nodoId);
    if (targetNode.length === 0) return;

    const neighborhood = targetNode.neighborhood().add(targetNode);

    // Opacar todo el grafo (Modo Fantasma extremo)
    cy.elements().removeClass('element-highlight').addClass('elements-faded');

    // Resaltar solo el área de interés y traer al frente
    neighborhood.removeClass('elements-faded').addClass('element-highlight');
    targetNode.style('z-index', 9999);
  }

  function performGraphSearch() {
    if (!cy || !graphSearchInput) return;
    const term = graphSearchInput.value.trim().toLowerCase();

    // Restaurar opacidades previas
    cy.elements().removeClass('elements-faded').removeClass('element-highlight');

    if (term === "") return;

    // Buscar nodo por ID exacto o que contenga el término
    const foundNodes = cy.nodes().filter(n => n.id().toLowerCase().includes(term));

    if (foundNodes.length > 0) {
      const targetNode = foundNodes[0];

      // Mostrar panel
      showNodeDetails(targetNode.id(), targetNode);

      // Aislar visualmente (Modo Aislamiento)
      aplicarModoAislamiento(targetNode.id());

      // Centrar y hacer flash (simulando clic en botón Focus)
      if (btnFocusNode) {
        btnFocusNode.click();
      }
    } else {
      alert("Término no encontrado en el grafo actual.");
    }
  }

  if (btnGraphSearch) {
    btnGraphSearch.addEventListener("click", performGraphSearch);
  }
  if (graphSearchInput) {
    graphSearchInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") performGraphSearch();
    });
  }

  const btnClearSearch = document.getElementById("btnClearSearch");
  if (btnClearSearch) {
    btnClearSearch.addEventListener("click", () => {
      if (graphSearchInput) graphSearchInput.value = "";
      if (cy) {
        cy.elements().removeClass('elements-faded').removeClass('element-highlight');
        cy.fit(); // Reajustar vista general
      }
    });
  }

  // Iniciar aplicación
  checkAuthStatus();

  // Cargar diccionarios automáticamente al iniciar
  console.log("Aplicación iniciada: Cargando lista de diccionarios...");
  loadDiccionarios().then((exito) => {
    if (exito) {
      const lastDic = localStorage.getItem("lastDiccionario");
      if (lastDic && Array.from(diccionarioSelect.options).some(o => o.value === lastDic)) {
        diccionarioSelect.value = lastDic;
        // Solo preseleccionamos en el dropdown, pero NO cargamos el grafo automáticamente.
        // if (loadDiccionarioBtn) {
        //   loadDiccionarioBtn.click();
        // }
      }
    }
  });

  // Detectar cambio de pestaña en Bootstrap para sincronizar el selector
  const allTabs = document.querySelectorAll('button[data-bs-toggle="tab"], a[data-bs-toggle="tab"]');
  allTabs.forEach(tabEl => {
    tabEl.addEventListener('shown.bs.tab', function (event) {
      // Si el usuario vuelve a una pestaña que necesita el selector actualizado
      if (typeof currentDiccionario !== 'undefined' && currentDiccionario && diccionarioSelect) {
        console.log("Sincronizando selector con:", currentDiccionario);
        diccionarioSelect.value = currentDiccionario;
      }
    });
  });

});

