const state = {
  manifest: null,
  dataset: null,
  activeTab: "main",
  filterText: "",
  cache: new Map(),
};

const els = {
  datasetCount: document.getElementById("dataset-count"),
  generatedAt: document.getElementById("generated-at"),
  picker: document.getElementById("dataset-picker"),
  title: document.getElementById("dataset-title"),
  description: document.getElementById("dataset-description"),
  downloadLink: document.getElementById("download-link"),
  summaryGrid: document.getElementById("summary-grid"),
  tabMain: document.getElementById("tab-main"),
  tabUncertainty: document.getElementById("tab-uncertainty"),
  search: document.getElementById("table-search"),
  tableSource: document.getElementById("table-source"),
  tableCount: document.getElementById("table-count"),
  tableStatus: document.getElementById("table-status"),
  tableContainer: document.getElementById("table-container"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatGeneratedAt(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function datasetById(id) {
  return state.manifest.datasets.find((item) => item.id === id);
}

function getActiveTableSpec(dataset) {
  return state.activeTab === "uncertainty" ? dataset.uncertainty : dataset.main;
}

function renderDatasetPicker() {
  els.picker.innerHTML = state.manifest.datasets
    .map(
      (dataset) => `
        <button
          class="pill ${state.dataset?.id === dataset.id ? "active" : ""}"
          type="button"
          data-dataset-id="${escapeHtml(dataset.id)}"
        >
          ${escapeHtml(dataset.label)}
        </button>
      `,
    )
    .join("");

  els.picker.querySelectorAll("[data-dataset-id]").forEach((button) => {
    button.addEventListener("click", () => selectDataset(button.dataset.datasetId));
  });
}

function renderSummary(dataset) {
  const tableSpec = getActiveTableSpec(dataset);
  const tableName = state.activeTab === "uncertainty" ? "Uncertainty" : "Main";
  els.summaryGrid.innerHTML = [
    { label: "Dataset", value: dataset.label },
    { label: "View", value: tableName },
    { label: "Rows", value: `${tableSpec.rowCount.toLocaleString()}` },
    { label: "Columns", value: `${tableSpec.columnCount.toLocaleString()}` },
  ]
    .map(
      (item) => `
        <div class="summary-card">
          <span class="label">${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
        </div>
      `,
    )
    .join("");
}

function renderTabs() {
  const uncertaintyDisabled = !state.dataset?.uncertainty;
  els.tabMain.classList.toggle("active", state.activeTab === "main");
  els.tabMain.setAttribute("aria-selected", String(state.activeTab === "main"));
  els.tabUncertainty.classList.toggle("active", state.activeTab === "uncertainty");
  els.tabUncertainty.setAttribute("aria-selected", String(state.activeTab === "uncertainty"));
  els.tabUncertainty.disabled = uncertaintyDisabled;
  els.tabUncertainty.title = uncertaintyDisabled ? "No uncertainty table available" : "";
}

function renderTable(data) {
  const query = state.filterText.trim().toLowerCase();
  const rows = query
    ? data.rows.filter((row) => row.some((cell) => String(cell ?? "").toLowerCase().includes(query)))
    : data.rows;

  const displayCount = `${rows.length.toLocaleString()} of ${data.rowCount.toLocaleString()} rows`;
  els.tableCount.textContent = displayCount;
  els.tableSource.textContent = data.source;

  if (rows.length === 0) {
    els.tableStatus.textContent = "No rows match the current filter.";
    els.tableContainer.innerHTML = '<div class="empty-state">Try a broader search term.</div>';
    return;
  }

  els.tableStatus.textContent = `${data.columnCount.toLocaleString()} columns loaded.`;
  const headerCells = data.columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("");
  const body = rows
    .map((row, idx) => {
      const cells = row
        .map((cell) => `<td>${escapeHtml(cell ?? "")}</td>`)
        .join("");
      return `<tr><td>${idx + 1}</td>${cells}</tr>`;
    })
    .join("");

  els.tableContainer.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>#</th>
          ${headerCells}
        </tr>
      </thead>
      <tbody>
        ${body}
      </tbody>
    </table>
  `;
}

function updateSelectedDatasetMeta(dataset) {
  const tableSpec = getActiveTableSpec(dataset);
  els.title.textContent = dataset.label;
  els.description.textContent = dataset.description;
  els.downloadLink.href = tableSpec.path;
  els.downloadLink.textContent = state.activeTab === "uncertainty" ? "Open uncertainty JSON" : "Open main JSON";
}

function renderCurrentDataset() {
  const dataset = state.dataset;
  if (!dataset) {
    return;
  }

  renderDatasetPicker();
  renderTabs();
  renderSummary(dataset);
  updateSelectedDatasetMeta(dataset);

  const spec = getActiveTableSpec(dataset);
  const cacheKey = `${dataset.id}:${state.activeTab}`;
  const cached = state.cache.get(cacheKey);
  if (cached) {
    renderTable(cached);
    return;
  }

  els.tableStatus.textContent = "Loading table data…";
  els.tableContainer.innerHTML = "";
  fetch(spec.path)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Failed to fetch ${spec.path} (${response.status})`);
      }
      return response.json();
    })
    .then((json) => {
      state.cache.set(cacheKey, json);
      renderTable(json);
    })
    .catch((error) => {
      els.tableStatus.textContent = "Failed to load the selected table.";
      els.tableContainer.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    });
}

async function selectDataset(datasetId) {
  const dataset = datasetById(datasetId);
  if (!dataset) {
    return;
  }
  state.dataset = dataset;
  state.activeTab = "main";
  state.filterText = "";
  els.search.value = "";
  renderCurrentDataset();
}

function wireUi() {
  els.tabMain.addEventListener("click", () => {
    if (state.activeTab !== "main") {
      state.activeTab = "main";
      state.filterText = "";
      els.search.value = "";
      renderCurrentDataset();
    }
  });

  els.tabUncertainty.addEventListener("click", () => {
    if (!state.dataset?.uncertainty) {
      return;
    }
    if (state.activeTab !== "uncertainty") {
      state.activeTab = "uncertainty";
      state.filterText = "";
      els.search.value = "";
      renderCurrentDataset();
    }
  });

  els.search.addEventListener("input", (event) => {
    state.filterText = event.target.value || "";
    const cacheKey = `${state.dataset.id}:${state.activeTab}`;
    const cached = state.cache.get(cacheKey);
    if (cached) {
      renderTable(cached);
    }
  });
}

async function main() {
  wireUi();
  const manifestResponse = await fetch("./manifest.json");
  if (!manifestResponse.ok) {
    throw new Error(`Failed to load manifest.json (${manifestResponse.status})`);
  }
  state.manifest = await manifestResponse.json();
  els.datasetCount.textContent = state.manifest.datasetCount.toLocaleString();
  els.generatedAt.textContent = formatGeneratedAt(state.manifest.generatedAt);
  renderDatasetPicker();
  await selectDataset(state.manifest.datasets[0].id);
}

main().catch((error) => {
  els.tableStatus.textContent = "The page could not be initialized.";
  els.tableContainer.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
});
