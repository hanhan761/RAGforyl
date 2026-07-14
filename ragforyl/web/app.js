const $ = (selector) => document.querySelector(selector);
const state = { status: null, graph: null };
let toastTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(payload?.detail || `请求失败（${response.status}）`);
  }
  return payload;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function showToast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("visible"), 2600);
}

function setInlineState(selector, message, isError = false) {
  const element = $(selector);
  element.textContent = message;
  element.classList.toggle("error", isError);
}

async function loadStatus() {
  const payload = await api("/api/status");
  state.status = payload;
  $("#version-label").textContent = `v${payload.version}`;
  const settings = payload.settings;
  $("#mode-badge").textContent = settings.llm_configured ? "LLM 增强模式" : "离线检索模式";
  renderSources(payload.sources);
  const ready = payload.index_ready;
  const badge = $("#index-badge");
  badge.textContent = ready ? `索引 ${payload.manifest.build_id}` : "尚未构建";
  badge.classList.toggle("offline", !ready);
  if (ready) {
    await loadGraph();
  } else {
    renderGraph({ nodes: [], edges: [], total_nodes: 0, total_edges: 0 });
  }
}

function renderSources(sources) {
  $("#source-count").textContent = `${sources.length} 个文件`;
  const list = $("#source-list");
  list.replaceChildren();
  for (const source of sources) {
    const item = document.createElement("div");
    item.className = "source-item";
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = source.name;
    const size = document.createElement("small");
    size.textContent = formatBytes(source.size_bytes);
    copy.append(name, size);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.title = `删除 ${source.name}`;
    remove.addEventListener("click", () => deleteSource(source.name));
    item.append(copy, remove);
    list.append(item);
  }
}

async function uploadFiles(files) {
  if (!files?.length) return;
  const form = new FormData();
  for (const file of files) form.append("files", file);
  setInlineState("#upload-state", `正在上传 ${files.length} 个文件…`);
  try {
    const payload = await api("/api/sources", { method: "POST", body: form });
    renderSources(payload.sources);
    setInlineState("#upload-state", `已加入 ${payload.saved.length} 个文件`);
    showToast("资料已加入，点击“开始构建”生成新图谱");
  } catch (error) {
    setInlineState("#upload-state", error.message, true);
  } finally {
    $("#file-input").value = "";
  }
}

async function deleteSource(filename) {
  try {
    const payload = await api(`/api/sources/${encodeURIComponent(filename)}`, { method: "DELETE" });
    renderSources(payload.sources);
    showToast("文件已移除，现有索引未受影响");
  } catch (error) {
    showToast(error.message);
  }
}

async function buildGraph() {
  const button = $("#build-button");
  button.disabled = true;
  button.textContent = "正在构建…";
  setInlineState("#build-state", "正在分块、抽取实体关系并执行质量检查，请勿关闭页面。", false);
  try {
    const payload = await api("/api/build", { method: "POST" });
    const manifest = payload.manifest;
    setInlineState(
      "#build-state",
      `完成：${manifest.node_count} 个节点，${manifest.edge_count} 条关系，${manifest.chunk_count} 个证据块。`,
    );
    showToast("知识图谱已构建并通过质量门禁");
    await loadStatus();
  } catch (error) {
    setInlineState("#build-state", error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "开始构建";
  }
}

async function submitQuery(event) {
  event.preventDefault();
  const question = $("#question-input").value.trim();
  if (!question) return;
  const button = $("#query-button");
  button.disabled = true;
  button.textContent = "检索中";
  try {
    const payload = await api("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: 7, generate_answer: true }),
    });
    renderResult(payload);
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "查询";
  }
}

function renderResult(payload) {
  const retrieval = payload.retrieval;
  $("#empty-result").hidden = true;
  $("#result-view").hidden = false;
  $("#answer-text").textContent = payload.answer;
  $("#confidence-label").textContent = `匹配度 ${Math.round(retrieval.confidence * 100)}%`;
  const chips = $("#node-chips");
  chips.replaceChildren();
  for (const node of retrieval.nodes) {
    const chip = document.createElement("span");
    chip.className = "node-chip";
    chip.textContent = `${node.name} · ${Math.round(node.score * 100)}%`;
    chips.append(chip);
  }
  $("#evidence-count").textContent = `${retrieval.sources.length} 条`;
  const evidenceList = $("#evidence-list");
  evidenceList.replaceChildren();
  for (const source of retrieval.sources) {
    const card = document.createElement("article");
    card.className = "evidence-card";
    const header = document.createElement("header");
    const reference = document.createElement("strong");
    reference.textContent = `[${source.reference}] ${source.section}`;
    const path = document.createElement("small");
    path.textContent = source.source_path;
    const text = document.createElement("p");
    text.textContent = source.text;
    header.append(reference, path);
    card.append(header, text);
    evidenceList.append(card);
  }
}

async function loadGraph() {
  try {
    state.graph = await api("/api/graph?limit=80");
    renderGraph(state.graph);
  } catch (error) {
    renderGraph({ nodes: [], edges: [], total_nodes: 0, total_edges: 0 });
  }
}

function renderGraph(graph) {
  const svg = $("#graph-canvas");
  svg.replaceChildren();
  $("#graph-count").textContent = `${graph.total_nodes} / ${graph.total_edges}`;
  $("#graph-placeholder").hidden = graph.nodes.length > 0;
  if (!graph.nodes.length) return;

  const width = 760;
  const height = 470;
  const center = { x: width / 2, y: height / 2 };
  const positions = new Map();
  graph.nodes.forEach((node, index) => {
    if (index === 0) {
      positions.set(node.id, center);
      return;
    }
    const ring = index <= 12 ? 1 : index <= 36 ? 2 : 3;
    const ringStart = ring === 1 ? 1 : ring === 2 ? 13 : 37;
    const ringCount = ring === 1 ? Math.min(12, graph.nodes.length - 1) : ring === 2 ? 24 : 44;
    const localIndex = index - ringStart;
    const angle = (Math.PI * 2 * localIndex) / ringCount - Math.PI / 2;
    const radiusX = ring * 103;
    const radiusY = ring * 59;
    positions.set(node.id, {
      x: center.x + Math.cos(angle) * radiusX,
      y: center.y + Math.sin(angle) * radiusY,
    });
  });

  const namespace = "http://www.w3.org/2000/svg";
  for (const edge of graph.edges) {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) continue;
    const line = document.createElementNS(namespace, "line");
    line.setAttribute("x1", source.x);
    line.setAttribute("y1", source.y);
    line.setAttribute("x2", target.x);
    line.setAttribute("y2", target.y);
    line.setAttribute("class", "graph-edge");
    const title = document.createElementNS(namespace, "title");
    title.textContent = edge.statement || edge.relation;
    line.append(title);
    svg.append(line);
  }

  graph.nodes.forEach((node, index) => {
    const position = positions.get(node.id);
    const group = document.createElementNS(namespace, "g");
    group.setAttribute("class", "graph-node");
    group.setAttribute("tabindex", "0");
    const circle = document.createElementNS(namespace, "circle");
    circle.setAttribute("cx", position.x);
    circle.setAttribute("cy", position.y);
    circle.setAttribute("r", index === 0 ? 13 : node.type === "topic" ? 9 : 7);
    circle.setAttribute("fill", nodeColor(node.type));
    circle.setAttribute("stroke", "#fff");
    circle.setAttribute("stroke-width", "2.5");
    const label = document.createElementNS(namespace, "text");
    label.setAttribute("x", position.x);
    label.setAttribute("y", position.y + (index === 0 ? 28 : 20));
    label.setAttribute("class", "graph-label");
    label.textContent = node.name.length > 9 ? `${node.name.slice(0, 8)}…` : node.name;
    const inspect = () => inspectNode(node);
    group.addEventListener("click", inspect);
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") inspect();
    });
    group.append(circle, label);
    svg.append(group);
  });
}

function nodeColor(type) {
  if (type === "topic") return "#c79a43";
  if (type === "term") return "#29495e";
  return "#176f68";
}

function inspectNode(node) {
  const inspector = $("#node-inspector");
  inspector.querySelector("span").textContent = node.type.toUpperCase();
  inspector.querySelector("h3").textContent = node.name;
  inspector.querySelector("p").textContent = node.description || "该节点已关联原始证据，暂无独立说明。";
}

function configureDropzone() {
  const dropzone = $("#dropzone");
  const input = $("#file-input");
  input.addEventListener("change", () => uploadFiles(input.files));
  for (const eventName of ["dragenter", "dragover"]) {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragging");
    });
  }
  for (const eventName of ["dragleave", "drop"]) {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragging");
    });
  }
  dropzone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files));
}

async function boot() {
  configureDropzone();
  $("#build-button").addEventListener("click", buildGraph);
  $("#query-form").addEventListener("submit", submitQuery);
  try {
    await loadStatus();
  } catch (error) {
    showToast(`初始化失败：${error.message}`);
  }
}

document.addEventListener("DOMContentLoaded", boot);
