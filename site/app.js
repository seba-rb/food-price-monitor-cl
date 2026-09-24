(() => {
  "use strict";

  const DATA_ROOT = new URL("data/", document.baseURI);
  const byId = (id) => document.getElementById(id);
  const elements = {
    appStatus: byId("app-status"),
    pageHero: byId("page-hero"),
    pageTitle: byId("page-title"),
    pageLede: byId("page-lede"),
    homeMetadata: byId("home-metadata"),
    headerNavLink: byId("header-nav-link"),
    scopeControls: byId("scope-controls"),
    dashboard: byId("dashboard-view"),
    scopeSummary: byId("scope-summary"),
    benchmarkNote: byId("benchmark-note"),
    benchmarkCards: byId("benchmark-cards"),
    moverRows: byId("movers-rows"),
    benchmarkRows: byId("benchmark-rows"),
    catalogPage: byId("catalog-page"),
    indexView: byId("index-view"),
    search: byId("product-search"),
    catalogSort: byId("catalog-sort"),
    catalogCount: byId("catalog-count"),
    catalogWeekLabel: byId("catalog-week-label"),
    catalogRows: byId("catalog-rows"),
    catalogTableWrap: byId("catalog-table-wrap"),
    catalogEmpty: byId("catalog-empty"),
    catalogEmptyTitle: byId("catalog-empty-title"),
    catalogEmptyCopy: byId("catalog-empty-copy"),
    clearSearch: byId("clear-search"),
    catalogRange: byId("catalog-range"),
    catalogPagination: byId("catalog-pagination"),
    regionFilter: byId("region-filter"),
    pointFilter: byId("point-filter"),
    catalogPointPicker: byId("catalog-point-picker"),
    catalogPointSummary: byId("catalog-point-summary"),
    catalogPointOptions: byId("catalog-point-options"),
    catalogPointsSelectAll: byId("catalog-points-select-all"),
    catalogPointsClear: byId("catalog-points-clear"),
    recentOnly: byId("recent-only"),
    freshnessNote: byId("freshness-note"),
    dataWeek: byId("data-week"),
    dataUpdated: byId("data-updated"),
    dataOmission: byId("data-omission"),
    openInterpretation: byId("open-interpretation"),
    openDataNotes: byId("open-data-notes"),
    infoDrawer: byId("info-drawer"),
    infoDrawerTitle: byId("info-drawer-title"),
    closeInfoDrawer: byId("close-info-drawer"),
    interpretationPanel: byId("interpretation-panel"),
    notesPanel: byId("notes-panel"),
    detail: byId("product-detail"),
    detailGroup: byId("detail-group"),
    detailTitle: byId("detail-title"),
    detailUnit: byId("detail-unit"),
    detailAliases: byId("detail-aliases"),
    detailScopeRegion: byId("detail-scope-region"),
    detailReferenceWeek: byId("detail-reference-week"),
    detailPointsCount: byId("detail-points-count"),
    detailPointsNote: byId("detail-points-note"),
    detailRangeValue: byId("detail-range-value"),
    detailRangeNote: byId("detail-range-note"),
    chartHeading: byId("chart-heading"),
    detailChartNote: byId("detail-chart-note"),
    detailPeriodNote: byId("detail-period-note"),
    detailRangeShortcuts: byId("detail-range-shortcuts"),
    chartModeSwitch: byId("chart-mode-switch"),
    chartModeHint: byId("chart-mode-hint"),
    comparisonSummary: byId("comparison-summary"),
    comparisonPeriod: byId("comparison-period"),
    comparisonMetrics: byId("comparison-metrics"),
    comparisonNote: byId("comparison-note"),
    ipcPublicationDate: byId("ipc-publication-date"),
    detailSeriesPicker: byId("detail-series-picker"),
    detailSeriesSummary: byId("detail-series-summary"),
    detailSeriesAvailability: byId("detail-series-availability"),
    detailSeriesList: byId("detail-series-list"),
    detailSeriesLegend: byId("detail-series-legend"),
    detailChartSummary: byId("detail-chart-summary"),
    historyDisclosure: byId("history-disclosure"),
    historyToggleLabel: byId("history-toggle-label"),
    historyPeriodLabel: byId("history-period-label"),
    detailRegion: byId("detail-region"),
    detailStatus: byId("detail-status"),
    historyRows: byId("history-rows"),
    chart: byId("price-chart"),
    back: byId("back-to-index"),
  };

  const currency = new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  });
  const percentage = new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const fullDate = new Intl.DateTimeFormat("es-CL", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  const shortDate = new Intl.DateTimeFormat("es-CL", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  const monthDate = new Intl.DateTimeFormat("es-CL", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  const indexNumber = new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  const seriesCache = new Map();
  let ipcCache = null;
  let indexData = null;
  let activeChart = null;
  let currentProductSlug = null;
  let detailRequestId = 0;
  let currentDetailSeriesProduct = null;
  let selectedDetailPointTypes = new Set();
  let detailRange = "max";
  let detailChartMode = "nominal";
  let currentIpcSeries = null;
  let catalogPageNumber = 1;
  let selectedCatalogPointTypes = new Set();
  const catalogPageSize = 20;
  const detailSeriesColors = ["#147a55", "#2563a6", "#a96400", "#c83e30", "#8654a8", "#087f83", "#667386"];
  const detailSeriesMarker = "circle";
  const detailSeriesSymbol = "●";

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function normalizeSearch(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("es-CL")
      .replace(/[’']/g, "")
      .replace(/\|/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function formatPrice(value) {
    return typeof value === "number" && Number.isFinite(value) ? currency.format(value) : "N/A";
  }

  function benchmarkUnit(unit) {
    const clean = String(unit || "").replace(/^\$\s*\/?\s*/, "").trim();
    const normalized = normalizeSearch(clean);
    if (normalized === "kilo") return "/ kg";
    if (normalized === "litro" || normalized === "caja de 1 litro") return "/ lt";
    if (normalized === "bandeja 12 unidades") return "/ bandeja 12 un.";
    return clean ? `/ ${clean.toLocaleLowerCase("es-CL")}` : "";
  }

  function formatChange(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return "N/A";
    const sign = value > 0 ? "+" : value < 0 ? "−" : "";
    return `${sign}${percentage.format(Math.abs(value))}\u00a0%`;
  }

  function formatDate(value, formatter = fullDate) {
    if (!value) return "Fecha no disponible";
    const parsed = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(parsed.getTime()) ? "Fecha no disponible" : formatter.format(parsed);
  }

  function formatMonth(value) {
    if (!value) return "Mes no disponible";
    const parsed = new Date(`${value}-01T00:00:00Z`);
    return Number.isNaN(parsed.getTime()) ? "Mes no disponible" : monthDate.format(parsed);
  }

  function monthOrdinal(value) {
    const [year, month] = String(value || "").split("-").map(Number);
    return Number.isFinite(year) && Number.isFinite(month) ? year * 12 + month - 1 : NaN;
  }

  function previousMonth(value, months) {
    const ordinal = monthOrdinal(value);
    if (!Number.isFinite(ordinal)) return "";
    const date = new Date(Date.UTC(Math.floor((ordinal - months) / 12), (ordinal - months) % 12, 1));
    return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
  }

  function productPresentation(product) {
    const parts = String(product.name || "").split("|").map((part) => part.trim()).filter(Boolean);
    if (parts.length < 2) return { name: product.name || "Producto sin nombre", metadata: "" };

    const normalized = (part) => normalizeSearch(part);
    const unknownValues = new Set(["", "sin especificar", "no especificado", "n/a"]);
    const nameParts = [parts[0]];
    const metadataParts = [];
    for (const part of parts.slice(1)) {
      if (unknownValues.has(normalized(part))) continue;
      if (["primera", "segunda", "tercera", "extra", "especial"].includes(normalized(part))) {
        metadataParts.push(`Calidad ${part.toLocaleLowerCase("es-CL")}`);
      } else if (nameParts.length < 3) {
        nameParts.push(part.toLocaleLowerCase("es-CL"));
      } else {
        metadataParts.push(part);
      }
    }
    return { name: nameParts.join(" "), metadata: metadataParts.join(" · ") };
  }

  function showStatus(container, message, options = {}) {
    container.replaceChildren();
    container.classList.toggle("status-message--error", Boolean(options.error));
    container.hidden = false;
    container.append(node("p", "status-message__text", message));
    if (options.retry) {
      const button = node("button", "text-button", options.retryLabel || "Intentar de nuevo");
      button.type = "button";
      button.addEventListener("click", options.retry, { once: true });
      container.append(button);
    }
  }

  function clearStatus(container) {
    container.replaceChildren();
    container.classList.remove("status-message--error");
    container.hidden = true;
  }

  function selectedSummary(product) {
    const byType = product.latest_by_point_type || {};
    return byType[elements.pointFilter.value] || null;
  }

  function selectedLocation(summary) {
    if (!summary) return null;
    if (elements.regionFilter.value === "national") return summary.national || null;
    return (summary.regions || {})[elements.regionFilter.value] || null;
  }

  function isRecentInSelectedScope(product) {
    return Boolean(selectedLocation(selectedSummary(product))?.fresh_within_28_days);
  }

  function updateFreshnessNote() {
    if (!indexData || !elements.freshnessNote) return;
    if (!elements.recentOnly.checked) {
      elements.freshnessNote.textContent = "Incluye también precios antiguos; revisa la semana de cada producto.";
      return;
    }
    const maxAgeDays = indexData.source?.freshness_policy?.max_age_days || 28;
    elements.freshnessNote.textContent = `Precios publicados en los últimos ${maxAgeDays} días para estos filtros.`;
  }

  function catalogChange(value, label) {
    const change = node("span", "index-change");
    if (typeof value !== "number" || !Number.isFinite(value)) {
      change.classList.add("index-change--na");
      change.textContent = "N/A";
      change.setAttribute("aria-label", `${label}: dato no disponible`);
      return change;
    }
    const direction = value > 0 ? "up" : value < 0 ? "down" : "flat";
    change.classList.add(`index-change--${direction}`);
    change.setAttribute("aria-label", `${label}: ${formatChange(value)}`);
    change.append(
      node("span", "index-change__arrow", value > 0 ? "↑" : value < 0 ? "↓" : "→"),
      node("span", "index-change__value", formatChange(value)),
    );
    return change;
  }

  function catalogRow(entry, referenceWeek) {
    const { group, product, presentation, price, pointTypeSlug, pointTypeLabel } = entry;
    const row = document.createElement("tr");
    row.className = "catalog-row";
    const name = document.createElement("th");
    name.scope = "row";
    const link = tableProductLink(product, presentation.name, pointTypeSlug);
    link.classList.add("catalog-product-link");
    const productDescription = [presentation.name, presentation.metadata, pointTypeLabel].filter(Boolean).join(" · ");
    link.setAttribute("aria-label", `Ver detalle de ${productDescription}, ${product.unit}`);
    name.append(link);
    if (presentation.metadata) name.append(node("span", "catalog-product__metadata", presentation.metadata));
    name.append(node("span", "catalog-product__unit", product.unit));

    const category = node("td", "catalog-category", group.group_name);
    const pointType = node("td", "catalog-point-type", pointTypeLabel);
    const current = node("td", "catalog-price numeric-column");
    if (price) {
      current.append(node("strong", "catalog-price__value", formatPrice(price.average_clp)));
      if (price.week_start && price.week_start !== referenceWeek) {
        current.append(node("small", "catalog-price__date", formatDate(price.week_start, shortDate)));
      }
    } else {
      current.append(node("span", "catalog-price__empty", "Sin datos"));
    }

    const weekly = node("td", "numeric-column");
    weekly.append(catalogChange(price?.wow_pct, "Variación semanal"));
    const yearly = node("td", "numeric-column");
    yearly.append(catalogChange(price?.yoy_pct, "Variación en 52 semanas"));
    const openCell = node("td", "catalog-open-cell");
    const openLink = tableProductLink(product, "›", pointTypeSlug);
    openLink.className = "catalog-open-link";
    openLink.setAttribute("aria-label", `Abrir historia de ${productDescription}`);
    openCell.append(openLink);
    row.append(name, category, pointType, current, weekly, yearly, openCell);
    row.addEventListener("click", (event) => {
      if (event.target.closest("a, button")) return;
      window.location.hash = productDetailHash(product, pointTypeSlug);
    });
    return row;
  }

  function catalogPageButton(label, page, options = {}) {
    const button = node("button", `page-button${options.current ? " page-button--current" : ""}`, label);
    button.type = "button";
    button.disabled = Boolean(options.disabled);
    if (options.current) button.setAttribute("aria-current", "page");
    if (options.ariaLabel) button.setAttribute("aria-label", options.ariaLabel);
    button.addEventListener("click", () => {
      catalogPageNumber = page;
      renderIndex();
      elements.catalogRows.closest("table")?.scrollIntoView({ block: "nearest" });
    });
    return button;
  }

  function renderCatalogPagination(totalPages) {
    const fragment = document.createDocumentFragment();
    fragment.append(catalogPageButton("‹", Math.max(1, catalogPageNumber - 1), {
      disabled: catalogPageNumber === 1,
      ariaLabel: "Página anterior",
    }));

    let pages;
    if (totalPages <= 7) {
      pages = Array.from({ length: totalPages }, (_, index) => index + 1);
    } else if (catalogPageNumber <= 3) {
      pages = [1, 2, 3, 4, "…", totalPages];
    } else if (catalogPageNumber >= totalPages - 2) {
      pages = [1, "…", totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
    } else {
      pages = [1, "…", catalogPageNumber - 1, catalogPageNumber, catalogPageNumber + 1, "…", totalPages];
    }
    for (const page of pages) {
      if (page === "…") {
        fragment.append(node("span", "pagination-ellipsis", "…"));
      } else {
        fragment.append(catalogPageButton(String(page), page, {
          current: page === catalogPageNumber,
          ariaLabel: `Página ${page}`,
        }));
      }
    }
    fragment.append(catalogPageButton("›", Math.min(totalPages, catalogPageNumber + 1), {
      disabled: catalogPageNumber === totalPages,
      ariaLabel: "Página siguiente",
    }));
    elements.catalogPagination.replaceChildren(fragment);
  }

  function renderIndex() {
    if (!indexData) return;
    const query = normalizeSearch(elements.search.value);
    const selectedPointTypes = (indexData.point_types || [])
      .filter(({ slug }) => selectedCatalogPointTypes.has(slug));
    const entries = allProducts().flatMap(({ group, product }) => {
      const presentation = productPresentation(product);
      const searchable = normalizeSearch(
        `${presentation.name} ${presentation.metadata} ${product.name} ${(product.aliases || []).join(" ")} ${product.unit} ${group.group_name}`,
      );
      return selectedPointTypes.flatMap((pointType) => {
        if (query && !searchable.includes(query) && !normalizeSearch(pointType.label).includes(query)) return [];
        const summary = (product.latest_by_point_type || {})[pointType.slug] || null;
        const price = selectedLocation(summary);
        if (!price) return [];
        return [{
          group,
          product,
          presentation,
          summary,
          price,
          pointTypeSlug: pointType.slug,
          pointTypeLabel: pointType.label,
        }];
      });
    });
    const matches = elements.recentOnly.checked
      ? entries.filter(({ price }) => Boolean(price?.fresh_within_28_days))
      : entries;

    const sort = elements.catalogSort.value;
    const compareName = (a, b) => a.presentation.name.localeCompare(b.presentation.name, "es-CL", { sensitivity: "base", numeric: true });
    const compareEntries = (a, b) => compareName(a, b)
      || a.pointTypeLabel.localeCompare(b.pointTypeLabel, "es-CL", { sensitivity: "base" });
    matches.sort((a, b) => {
      if (sort === "name") return compareEntries(a, b);
      if (sort === "price-desc" || sort === "price-asc") {
        const direction = sort === "price-desc" ? -1 : 1;
        const aValue = a.price?.average_clp;
        const bValue = b.price?.average_clp;
        if (!Number.isFinite(aValue)) return Number.isFinite(bValue) ? 1 : compareEntries(a, b);
        if (!Number.isFinite(bValue)) return -1;
        return direction * (aValue - bValue) || compareEntries(a, b);
      }
      const direction = sort === "change-up" ? -1 : 1;
      const aValue = a.price?.wow_pct;
      const bValue = b.price?.wow_pct;
      if (!Number.isFinite(aValue)) return Number.isFinite(bValue) ? 1 : compareEntries(a, b);
      if (!Number.isFinite(bValue)) return -1;
      return direction * (aValue - bValue) || compareEntries(a, b);
    });

    const total = matches.length;
    const totalPages = Math.ceil(total / catalogPageSize);
    catalogPageNumber = Math.min(Math.max(catalogPageNumber, 1), Math.max(totalPages, 1));
    const start = (catalogPageNumber - 1) * catalogPageSize;
    const pageEntries = matches.slice(start, start + catalogPageSize);
    const referenceWeek = matches.reduce((latest, entry) => {
      const week = entry.price?.week_start;
      return week && (!latest || week > latest) ? week : latest;
    }, "");

    elements.catalogCount.textContent = String(total);
    elements.catalogWeekLabel.textContent = referenceWeek ? `Semana ${formatDate(referenceWeek, shortDate)}` : "Sin semana disponible";
    elements.catalogRows.replaceChildren(...pageEntries.map((entry) => catalogRow(entry, referenceWeek)));
    elements.catalogTableWrap.hidden = total === 0;
    elements.catalogEmpty.hidden = total !== 0;
    elements.catalogPagination.hidden = totalPages < 2;

    if (total === 0) {
      const hasSearch = Boolean(elements.search.value.trim());
      const noPointTypes = selectedCatalogPointTypes.size === 0;
      const freshnessExcluded = elements.recentOnly.checked && entries.length > 0;
      elements.catalogEmptyTitle.textContent = noPointTypes
        ? "Selecciona al menos un punto de monitoreo"
        : freshnessExcluded
          ? hasSearch ? `No hay datos recientes para “${elements.search.value.trim()}”` : "No hay registros recientes para estos filtros"
        : hasSearch
          ? `No encontramos productos para “${elements.search.value.trim()}”`
          : "No hay registros para esta selección";
      elements.catalogEmptyCopy.textContent = noPointTypes
        ? "Selecciona uno o más puntos de monitoreo para ver sus precios."
        : freshnessExcluded
          ? "Prueba con otra región o desactiva el filtro de datos recientes para consultar el historial disponible."
          : "Prueba con otro nombre o ajusta la región y los puntos de monitoreo.";
      elements.clearSearch.hidden = !hasSearch;
      elements.catalogRange.textContent = "No hay productos que mostrar.";
      elements.catalogPagination.replaceChildren();
      return;
    }

    const last = Math.min(start + catalogPageSize, total);
    elements.catalogRange.textContent = `Mostrando ${start + 1}–${last} de ${total} ${total === 1 ? "resultado" : "resultados"}`;
    elements.clearSearch.hidden = true;
    renderCatalogPagination(totalPages);
  }

  function allProducts() {
    return (indexData.groups || []).flatMap((group) =>
      (group.products || []).map((product) => ({ group, product })),
    );
  }

  function selectedScopeLabels() {
    const point = elements.pointFilter.options[elements.pointFilter.selectedIndex]?.text || "Punto de monitoreo";
    const region = elements.regionFilter.options[elements.regionFilter.selectedIndex]?.text || "Nacional";
    return { point, region };
  }

  function selectedBenchmarks() {
    return allProducts()
      .map(({ group, product }) => ({
        group,
        product,
        rank: product.benchmark?.rank_by_point_type?.[elements.pointFilter.value],
        summary: latestLocationSummary(product, elements.pointFilter.value, elements.regionFilter.value),
      }))
      .filter(({ rank, summary }) => Number.isInteger(rank) && summary?.fresh_within_28_days)
      .sort((a, b) => a.rank - b.rank);
  }

  function selectedTrend(product) {
    const byScope = (product.trend_by_point_type || {})[elements.pointFilter.value];
    if (!byScope) return [];
    if (elements.regionFilter.value === "national") return byScope.national || [];
    return (byScope.regions || {})[elements.regionFilter.value] || [];
  }

  function svgElement(tag, className) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    if (className) element.setAttribute("class", className);
    return element;
  }

  function renderSparkline(points, product, summary) {
    if (points.length < 2) {
      return node("p", "sparkline-empty", "Historia breve");
    }
    const width = 260;
    const height = 58;
    const inset = 5;
    const values = points.map((point) => point.average_clp);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || Math.max(max * 0.08, 1);
    const coordinates = values.map((value, index) => ({
      x: inset + (index / (values.length - 1)) * (width - inset * 2),
      y: height - inset - ((value - min) / span) * (height - inset * 2),
    }));
    const svg = svgElement("svg", "sparkline");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      `${product.benchmark.label}: evolución semanal durante ${points.length} semanas, desde ${formatDate(points[0].week_start, shortDate)} hasta ${formatDate(points.at(-1).week_start, shortDate)}.`,
    );
    const baseline = svgElement("path", "sparkline__baseline");
    baseline.setAttribute("d", `M${inset} ${height - inset}H${width - inset}`);
    const line = svgElement("path", `sparkline__line ${summary.wow_pct > 0 ? "sparkline__line--up" : summary.wow_pct < 0 ? "sparkline__line--down" : ""}`.trim());
    line.setAttribute("d", coordinates.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" "));
    line.setAttribute("vector-effect", "non-scaling-stroke");
    const endpoint = svgElement("circle", "sparkline__endpoint");
    endpoint.setAttribute("cx", coordinates.at(-1).x.toFixed(2));
    endpoint.setAttribute("cy", coordinates.at(-1).y.toFixed(2));
    endpoint.setAttribute("r", "3");
    svg.append(baseline, line, endpoint);
    return svg;
  }

  function movementBadge(value, label = "vs semana anterior") {
    const badge = node("span", "movement-badge");
    if (typeof value !== "number" || !Number.isFinite(value)) {
      badge.classList.add("movement-badge--na");
      badge.append(node("span", "movement-badge__value", "N/A"));
      badge.setAttribute("aria-label", `${label}: no hay suficientes observaciones para calcular la variación.`);
      badge.title = "No hay suficientes observaciones para calcular esta variación.";
      return badge;
    }
    const direction = value > 0 ? "up" : value < 0 ? "down" : "flat";
    badge.classList.add(`movement-badge--${direction}`);
    badge.setAttribute("aria-label", `${label}: ${formatChange(value)}`);
    badge.append(
      node("span", "movement-badge__arrow", value > 0 ? "↑" : value < 0 ? "↓" : "→"),
      node("span", "movement-badge__value", formatChange(value)),
    );
    return badge;
  }

  function renderBenchmarkCard(item) {
    const { group, product, summary } = item;
    const presentation = productPresentation(product);
    const card = node("article", "benchmark-card");
    const head = node("div", "benchmark-card__head");
    const title = node("a", "benchmark-card__title", product.benchmark.label || presentation.name);
    title.href = productDetailHash(product, elements.pointFilter.value);
    title.setAttribute("aria-label", `Ver historia de ${product.name}, ${product.unit}`);
    head.append(title, movementBadge(summary.wow_pct));
    card.append(head, node("p", "benchmark-card__family", group.group_name));

    const price = node("strong", "benchmark-card__price", formatPrice(summary.average_clp));
    card.append(price, node("p", "benchmark-card__unit", benchmarkUnit(product.unit)));

    const trend = selectedTrend(product);
    card.append(renderSparkline(trend, product, summary));
    const range = node("div", "sparkline-range");
    range.append(
      node("span", "sparkline-range__start", trend.length ? formatDate(trend[0].week_start, shortDate) : ""),
      node("span", "sparkline-range__label", "últimas 52 semanas"),
      node("span", "sparkline-range__end", trend.length ? formatDate(trend.at(-1).week_start, shortDate) : ""),
    );
    card.append(range);
    return card;
  }

  function productDetailHash(product, pointTypeSlug = "") {
    const pointQuery = pointTypeSlug ? `?point=${encodeURIComponent(pointTypeSlug)}` : "";
    return `#/producto/${encodeURIComponent(product.slug)}${pointQuery}`;
  }

  function tableProductLink(product, label, pointTypeSlug = "") {
    const link = node("a", "market-product-link", label || productPresentation(product).name);
    link.href = productDetailHash(product, pointTypeSlug);
    return link;
  }

  function tablePriceCell(summary, date, className = "") {
    const cell = node("td", `market-price ${className}`.trim());
    cell.append(node("strong", "market-price__value", formatPrice(summary)));
    cell.append(node("span", "market-price__date", date ? formatDate(date, shortDate) : "Sin comparación"));
    return cell;
  }

  function tableEmptyRow(tbody, columns, message) {
    const row = document.createElement("tr");
    const cell = node("td", "market-table__empty", message);
    cell.colSpan = columns;
    row.append(cell);
    tbody.replaceChildren(row);
  }

  function renderMoverTable() {
    const movers = allProducts()
      .map(({ group, product }) => ({
        group,
        product,
        summary: latestLocationSummary(product, elements.pointFilter.value, elements.regionFilter.value),
      }))
      .filter(({ summary }) => summary?.fresh_within_28_days && Number.isFinite(summary.wow_pct))
      .sort((a, b) => Math.abs(b.summary.wow_pct) - Math.abs(a.summary.wow_pct))
      .slice(0, 10);

    if (!movers.length) {
      tableEmptyRow(elements.moverRows, 4, "No hay variaciones semanales recientes para este punto y ámbito.");
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const { product, summary } of movers) {
      const row = document.createElement("tr");
      const name = document.createElement("th");
      name.scope = "row";
      const presentation = productPresentation(product);
      name.append(tableProductLink(product, presentation.name));
      if (presentation.metadata) name.append(node("span", "market-product-unit", presentation.metadata));
      const previous = tablePriceCell(summary.previous_average_clp, summary.previous_week_start, "market-price--previous");
      const latest = tablePriceCell(summary.average_clp, summary.week_start, "market-price--latest");
      const change = node("td", "market-change");
      change.append(movementBadge(summary.wow_pct));
      row.append(name, previous, latest, change);
      fragment.append(row);
    }
    elements.moverRows.replaceChildren(fragment);
  }

  function renderBenchmarkTable(benchmarks) {
    if (!benchmarks.length) {
      tableEmptyRow(elements.benchmarkRows, 5, "Los referentes no tienen datos recientes para esta combinación.");
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const { product, summary } of benchmarks) {
      const row = document.createElement("tr");
      const name = document.createElement("th");
      name.scope = "row";
      name.append(tableProductLink(product, product.benchmark.label, elements.pointFilter.value));
      const unit = node("span", "market-product-unit", product.unit);
      name.append(unit);
      const price = node("td", "numeric-column market-table__number", formatPrice(summary.average_clp));
      const weekly = node("td", "numeric-column market-change");
      weekly.append(movementBadge(summary.wow_pct));
      const yearly = node("td", "numeric-column market-change");
      yearly.append(movementBadge(summary.yoy_pct, "vs hace 52 semanas"));
      const week = node("td", "numeric-column market-table__week", formatDate(summary.week_start, shortDate));
      row.append(name, price, weekly, yearly, week);
      fragment.append(row);
    }
    elements.benchmarkRows.replaceChildren(fragment);
  }

  function renderDashboard() {
    if (!indexData) return;
    const labels = selectedScopeLabels();
    elements.scopeSummary.textContent = `${labels.point} · ${labels.region}`;
    const benchmarks = selectedBenchmarks();
    const referenceWeek = indexData.latest_week_start
      ? `Semana de referencia ${formatDate(indexData.latest_week_start)}; la tabla indica la semana de cada precio.`
      : "La tabla indica la semana de cada precio.";
    elements.benchmarkNote.textContent = labels.point === "Mercado Mayorista"
      ? `La cobertura reciente de este punto se concentra en legumbres. ${referenceWeek}`
      : `Referentes seleccionados para este punto de monitoreo. ${referenceWeek}`;
    elements.benchmarkCards.replaceChildren();
    if (!benchmarks.length) {
      const empty = node("p", "dashboard-empty", "No hay benchmarks con datos recientes para este punto y ámbito. Prueba otra combinación.");
      elements.benchmarkCards.append(empty);
    } else {
      const fragment = document.createDocumentFragment();
      for (const benchmark of benchmarks) fragment.append(renderBenchmarkCard(benchmark));
      elements.benchmarkCards.append(fragment);
    }
    renderMoverTable();
    renderBenchmarkTable(benchmarks);
  }

  function updateCatalogPointPicker() {
    const available = indexData.point_types || [];
    const selectedCount = selectedCatalogPointTypes.size;
    elements.catalogPointSummary.textContent = selectedCount === available.length
      ? "Todos los puntos de monitoreo"
      : selectedCount === 0
        ? "Ningún punto seleccionado"
        : `${selectedCount} seleccionados`;
    elements.catalogPointsSelectAll.disabled = selectedCount === available.length;
    elements.catalogPointsClear.disabled = selectedCount === 0;
  }

  function populateCatalogPointPicker() {
    elements.catalogPointOptions.replaceChildren();
    for (const pointType of indexData.point_types || []) {
      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = `catalog-point-${pointType.slug}`;
      input.value = pointType.slug;
      input.checked = selectedCatalogPointTypes.has(pointType.slug);
      input.setAttribute("aria-label", pointType.label);
      const label = node("label", "catalog-point-option");
      label.htmlFor = input.id;
      label.append(input, node("span", "", pointType.label));
      elements.catalogPointOptions.append(label);
    }
    updateCatalogPointPicker();
  }

  function populateFilters() {
    elements.regionFilter.replaceChildren(new Option("Nacional · regiones con datos", "national"));
    for (const region of indexData.regions || []) {
      elements.regionFilter.add(new Option(region.name, String(region.id)));
    }

    elements.pointFilter.replaceChildren();
    for (const pointType of indexData.point_types || []) {
      elements.pointFilter.add(new Option(pointType.label, pointType.slug));
    }
    const supermarket = (indexData.point_types || []).find(
      (pointType) => normalizeSearch(pointType.label) === "supermercado",
    );
    elements.pointFilter.value = supermarket?.slug || indexData.point_types?.[0]?.slug || "";
    selectedCatalogPointTypes = new Set((indexData.point_types || []).map(({ slug }) => slug));
    populateCatalogPointPicker();
    updateFreshnessNote();
  }

  function updateSourceStamp() {
    elements.dataWeek.textContent = indexData.latest_week_start
      ? formatDate(indexData.latest_week_start)
      : "Semana no disponible";
    if (indexData.data_updated_at) {
      const timestamp = new Date(indexData.data_updated_at);
      elements.dataUpdated.textContent = Number.isNaN(timestamp.getTime())
        ? "Actualización registrada por ODEPA"
        : new Intl.DateTimeFormat("es-CL", { dateStyle: "long", timeZone: "UTC" }).format(timestamp);
    }
    const messages = (indexData.source?.excluded_years || [])
      .map(({ year, reason }) => `Año ${year} omitido: ${reason}`);
    const omittedByYear = new Map();
    for (const resource of indexData.source?.resources || []) {
      for (const observation of resource.excluded_observations || []) {
        const year = observation.year || resource.year;
        if (!omittedByYear.has(year)) omittedByYear.set(year, []);
        omittedByYear.get(year).push(observation);
      }
    }
    for (const [year, observations] of omittedByYear) {
      const products = [...new Set(observations.map(({ product_name }) => product_name).filter(Boolean))];
      const reasons = [...new Set(observations.map(({ reason }) => reason).filter(Boolean))];
      const productSummary = products.length ? ` (${products.join(" y ")})` : "";
      const reasonSummary = reasons.length ? ` ${reasons.join(" ")}` : "";
      messages.push(`Se omitieron ${observations.length} observaciones de ${year}${productSummary}.${reasonSummary}`);
    }
    elements.dataOmission.hidden = messages.length === 0;
    elements.dataOmission.textContent = messages.join(" ");
  }

  function openInfoDrawer(panel) {
    const showNotes = panel === "notes";
    elements.interpretationPanel.hidden = showNotes;
    elements.notesPanel.hidden = !showNotes;
    elements.infoDrawerTitle.textContent = showNotes ? "Notas y cobertura" : "Cómo interpretar estos datos";
    if (!elements.infoDrawer.open) elements.infoDrawer.showModal();
  }

  function findProduct(slug) {
    for (const group of indexData.groups || []) {
      const product = (group.products || []).find((item) => item.slug === slug);
      if (product) return { group, product };
    }
    return null;
  }

  async function loadGroupSeries(group) {
    if (seriesCache.has(group.slug)) return seriesCache.get(group.slug);
    const request = (async () => {
      const url = new URL(group.series_url, DATA_ROOT);
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`No se pudo cargar la historia (HTTP ${response.status}).`);
      const document = await response.json();
      if (document.schema_version !== 1 || document.group_slug !== group.slug || !document.products) {
        throw new Error("El archivo de historia tiene un formato que esta página no reconoce.");
      }
      return document;
    })();
    seriesCache.set(group.slug, request);
    try {
      return await request;
    } catch (error) {
      seriesCache.delete(group.slug);
      throw error;
    }
  }

  async function loadIpcSeries() {
    if (ipcCache) return ipcCache;
    const request = (async () => {
      const response = await fetch(new URL("ipc.json", DATA_ROOT), {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`No se pudo cargar el IPC (HTTP ${response.status}).`);
      const document = await response.json();
      if (document.schema_version !== 1 || !document.source || !document.observations) {
        throw new Error("El archivo de IPC tiene un formato que esta página no reconoce.");
      }
      const points = Object.entries(document.observations)
        .map(([month, index]) => ({ month, index: Number(index) }))
        .filter(({ month, index }) => /^\d{4}-\d{2}$/.test(month) && Number.isFinite(index) && index > 0)
        .sort((left, right) => left.month.localeCompare(right.month));
      if (points.length < 6 || points.at(-1)?.month !== document.source.latest_month) {
        throw new Error("La serie de IPC está incompleta o no coincide con su última fecha publicada.");
      }
      return { ...document, points, byMonth: new Map(points.map((point) => [point.month, point.index])) };
    })();
    ipcCache = request;
    try {
      return await request;
    } catch (error) {
      ipcCache = null;
      throw error;
    }
  }

  function latestLocationSummary(product, pointSlug, regionValue) {
    const summary = (product.latest_by_point_type || {})[pointSlug];
    if (!summary) return null;
    return regionValue === "national" ? summary.national : (summary.regions || {})[regionValue];
  }

  function pointTypeLabel(slug) {
    return (indexData.point_types || []).find((pointType) => pointType.slug === slug)?.label || slug;
  }

  function pointSeriesForRegion(pointSeries, regionValue) {
    if (!pointSeries) return [];
    if (regionValue === "national") return pointSeries.national || [];
    return (pointSeries.regions || {})[regionValue] || [];
  }

  function availableDetailPointTypes(seriesProduct) {
    const pointTypes = seriesProduct.point_types || {};
    return (indexData.point_types || [])
      .map((pointType) => pointType.slug)
      .filter((slug) => {
        const pointSeries = pointTypes[slug];
        return Boolean(pointSeries && (
          (pointSeries.national || []).length
          || Object.values(pointSeries.regions || {}).some((points) => points.length)
        ));
      });
  }

  function populateDetailRegions(seriesProduct) {
    const previousRegion = elements.detailRegion.value;
    const regions = new Set();
    for (const pointSeries of Object.values(seriesProduct.point_types || {})) {
      for (const [regionId, points] of Object.entries(pointSeries.regions || {})) {
        if (points.length) regions.add(regionId);
      }
    }
    const regionsById = new Map((indexData.regions || []).map((region) => [String(region.id), region.name]));
    elements.detailRegion.replaceChildren(new Option("Nacional · regiones con datos", "national"));
    for (const regionId of [...regions].sort((a, b) => Number(a) - Number(b))) {
      elements.detailRegion.add(new Option(regionsById.get(regionId) || `Región ${regionId}`, regionId));
    }
    elements.detailRegion.value = [...elements.detailRegion.options].some((option) => option.value === previousRegion)
      ? previousRegion
      : "national";
  }

  function updateDetailSeriesPicker(seriesProduct) {
    const available = availableDetailPointTypes(seriesProduct);
    const selectedCount = selectedDetailPointTypes.size;
    elements.detailSeriesSummary.textContent = selectedCount === 0
      ? "Ninguno seleccionado"
      : selectedCount === available.length
        ? `Todos (${available.length})`
        : `${selectedCount} de ${available.length}`;
    elements.detailSeriesAvailability.textContent = available.length
      ? `${available.length} ${available.length === 1 ? "punto disponible" : "puntos disponibles"} para este producto.`
      : "Este producto no tiene series de monitoreo disponibles.";
  }

  function populateDetailPointTypes(seriesProduct, preferredSlug = "") {
    const available = availableDetailPointTypes(seriesProduct);
    selectedDetailPointTypes = new Set(available.includes(preferredSlug) ? [preferredSlug] : available);
    elements.detailSeriesList.replaceChildren();
    for (const [index, slug] of available.entries()) {
      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = `detail-point-${slug}`;
      input.value = slug;
      input.checked = selectedDetailPointTypes.has(slug);
      input.setAttribute("aria-label", pointTypeLabel(slug));
      const pointTypeIndex = (indexData.point_types || []).findIndex((pointType) => pointType.slug === slug);
      input.dataset.seriesColor = detailSeriesColors[Math.max(pointTypeIndex, index) % detailSeriesColors.length];
      const marker = node("span", "series-option__marker", detailSeriesSymbol);
      marker.style.setProperty("--series-color", input.dataset.seriesColor);
      marker.setAttribute("aria-hidden", "true");
      const label = node("label", "series-option");
      label.htmlFor = input.id;
      label.append(input, marker, node("span", "series-option__name", pointTypeLabel(slug)));
      elements.detailSeriesList.append(label);
    }
    updateDetailSeriesPicker(seriesProduct);
  }

  function selectedDetailSeries(seriesProduct) {
    const pointTypes = seriesProduct.point_types || {};
    return availableDetailPointTypes(seriesProduct)
      .filter((slug) => selectedDetailPointTypes.has(slug))
      .map((slug) => {
        const order = (indexData.point_types || []).findIndex((pointType) => pointType.slug === slug);
        return {
          slug,
          label: pointTypeLabel(slug),
          color: detailSeriesColors[Math.max(order, 0) % detailSeriesColors.length],
          marker: detailSeriesMarker,
          symbol: detailSeriesSymbol,
          points: pointSeriesForRegion(pointTypes[slug], elements.detailRegion.value),
        };
      });
  }

  function renderDetailSummary(seriesProduct, activeSeries) {
    const regionLabel = elements.detailRegion.options[elements.detailRegion.selectedIndex]?.text || "Nacional · regiones con datos";
    const availableInRegion = availableDetailPointTypes(seriesProduct)
      .filter((slug) => pointSeriesForRegion(seriesProduct.point_types[slug], elements.detailRegion.value).length);
    const latestWeek = activeSeries
      .flatMap((series) => series.points.map((point) => point.week_start))
      .sort()
      .at(-1);
    const latestAverages = latestWeek
      ? activeSeries.flatMap((series) => series.points
        .filter((point) => point.week_start === latestWeek && Number.isFinite(point.average_clp))
        .map((point) => point.average_clp))
      : [];

    elements.detailScopeRegion.textContent = regionLabel;
    elements.detailReferenceWeek.textContent = latestWeek ? formatDate(latestWeek, shortDate) : "Sin datos";
    elements.detailPointsCount.textContent = String(availableInRegion.length);
    elements.detailPointsNote.textContent = elements.detailRegion.value === "national"
      ? "Con historial disponible"
      : "Con datos en esta región";
    if (latestAverages.length) {
      const minimum = Math.min(...latestAverages);
      const maximum = Math.max(...latestAverages);
      elements.detailRangeValue.textContent = minimum === maximum
        ? formatPrice(minimum)
        : `${formatPrice(minimum)} – ${formatPrice(maximum)}`;
      elements.detailRangeNote.textContent = `${latestAverages.length} ${latestAverages.length === 1 ? "punto con dato" : "puntos con datos"} en esa semana`;
    } else {
      elements.detailRangeValue.textContent = "N/A";
      elements.detailRangeNote.textContent = "Sin promedios para comparar";
    }
  }

  function weekDate(value) {
    if (!value) return null;
    const date = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function dateMonthsBefore(date, months) {
    const target = new Date(date.getTime());
    const day = target.getUTCDate();
    target.setUTCDate(1);
    target.setUTCMonth(target.getUTCMonth() - months);
    const lastDayOfMonth = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
    target.setUTCDate(Math.min(day, lastDayOfMonth));
    return target;
  }

  function seriesForSelectedRange(seriesList) {
    const latestWeek = seriesList
      .flatMap((series) => series.points.map((point) => point.week_start))
      .sort()
      .at(-1);
    if (detailRange === "max" || !latestWeek) return seriesList;
    const latestDate = weekDate(latestWeek);
    const months = detailRange === "1y" ? 12 : 60;
    const cutoff = latestDate && dateMonthsBefore(latestDate, months);
    if (!cutoff) return seriesList;
    return seriesList.map((series) => ({
      ...series,
      points: series.points.filter((point) => {
        const date = weekDate(point.week_start);
        return date && date >= cutoff;
      }),
    })).filter((series) => series.points.length);
  }

  function updateRangeShortcuts(seriesList) {
    const latestWeek = seriesList
      .flatMap((series) => series.points.map((point) => point.week_start))
      .sort()
      .at(-1);
    const latestDate = weekDate(latestWeek);
    for (const button of elements.detailRangeShortcuts.querySelectorAll("[data-detail-range]")) {
      const range = button.dataset.detailRange;
      const months = range === "1y" ? 12 : range === "5y" ? 60 : null;
      const cutoff = months && latestDate ? dateMonthsBefore(latestDate, months) : null;
      const hasDataInRange = !months || seriesList.some((series) => series.points.some((point) => {
        const date = weekDate(point.week_start);
        return date && date >= cutoff;
      }));
      button.disabled = !latestDate || !hasDataInRange;
      button.setAttribute("aria-pressed", String(range === detailRange));
    }
  }

  function renderSeriesLegend(seriesList) {
    elements.detailSeriesLegend.replaceChildren();
    for (const series of seriesList) {
      const item = node("span", "series-legend__item");
      const marker = node("span", series.legendType === "line"
        ? "series-legend__marker series-legend__marker--line"
        : "series-legend__marker", series.symbol || "");
      marker.style.setProperty("--series-color", series.color);
      marker.setAttribute("aria-hidden", "true");
      item.append(marker, node("span", "series-legend__name", series.label));
      elements.detailSeriesLegend.append(item);
    }
  }

  function monthlyAveragePrices(series, firstMonth, lastMonth) {
    const monthlyTotals = new Map();
    for (const point of series.points) {
      const month = point.week_start.slice(0, 7);
      if (month < firstMonth || month > lastMonth || !Number.isFinite(point.average_clp)) continue;
      const total = monthlyTotals.get(month) || { sum: 0, count: 0 };
      total.sum += point.average_clp;
      total.count += 1;
      monthlyTotals.set(month, total);
    }
    return new Map([...monthlyTotals.entries()].map(([month, total]) => [month, total.sum / total.count]));
  }

  function buildInflationComparison(seriesList, ipcSeries) {
    const latestIpcMonth = ipcSeries.points.at(-1)?.month;
    const rangeLength = detailRange === "1y" ? 12 : detailRange === "5y" ? 60 : null;
    const firstAllowedMonth = rangeLength ? previousMonth(latestIpcMonth, rangeLength) : "0000-00";
    const availableSeries = seriesList.map((series) => ({
      ...series,
      monthlyPrices: monthlyAveragePrices(series, firstAllowedMonth, latestIpcMonth),
    }));
    const eligible = [];
    const omitted = [];
    for (const series of availableSeries) {
      const months = [...series.monthlyPrices.keys()].sort();
      const hasEnoughHistory = months.length >= 6
        && monthOrdinal(months.at(-1)) - monthOrdinal(months[0]) >= 5;
      if (hasEnoughHistory) eligible.push(series);
      else omitted.push(series.label);
    }
    if (!eligible.length) return { eligible, omitted, reason: "No hay puntos con al menos seis meses de observaciones en este período." };

    const sharedMonths = ipcSeries.points
      .map(({ month }) => month)
      .filter((month) => month >= firstAllowedMonth && month <= latestIpcMonth
        && eligible.every((series) => series.monthlyPrices.has(month)));
    if (sharedMonths.length < 6 || monthOrdinal(sharedMonths.at(-1)) - monthOrdinal(sharedMonths[0]) < 5) {
      return { eligible, omitted, reason: "Los puntos seleccionados no comparten suficientes meses para una comparación consistente." };
    }

    const baseMonth = sharedMonths[0];
    const endMonth = sharedMonths.at(-1);
    const baseIpc = ipcSeries.byMonth.get(baseMonth);
    const endIpc = ipcSeries.byMonth.get(endMonth);
    const inflationChange = (endIpc / baseIpc - 1) * 100;
    const months = ipcSeries.points
      .map(({ month }) => month)
      .filter((month) => month >= baseMonth && month <= endMonth);
    const normalizedSeries = eligible.map((series) => {
      const basePrice = series.monthlyPrices.get(baseMonth);
      const endPrice = series.monthlyPrices.get(endMonth);
      const nominalChange = (endPrice / basePrice - 1) * 100;
      const realChange = ((endPrice / basePrice) / (endIpc / baseIpc) - 1) * 100;
      return {
        ...series,
        basePrice,
        endPrice,
        nominalChange,
        realChange,
        data: months.map((month) => {
          const price = series.monthlyPrices.get(month);
          return Number.isFinite(price) ? price / basePrice * 100 : null;
        }),
      };
    });
    const normalizedIpc = months.map((month) => ipcSeries.byMonth.get(month) / baseIpc * 100);
    return {
      eligible: normalizedSeries,
      omitted,
      months,
      baseMonth,
      endMonth,
      inflationChange,
      ipcData: normalizedIpc,
      reason: "",
    };
  }

  function comparisonMetric(label, color, value, detail, isReference = false) {
    const card = node("article", "comparison-metric");
    const labelRow = node("span", "comparison-metric__label");
    const swatch = node("span", isReference
      ? "comparison-metric__swatch comparison-metric__swatch--line"
      : "comparison-metric__swatch");
    swatch.style.setProperty("--series-color", color);
    swatch.setAttribute("aria-hidden", "true");
    labelRow.append(swatch, node("span", "", label));
    const formattedValue = node("strong", "comparison-metric__value", formatChange(value) + (isReference ? "" : " real"));
    if (!isReference && value > 0) formattedValue.classList.add("comparison-metric__value--up");
    if (!isReference && value < 0) formattedValue.classList.add("comparison-metric__value--down");
    card.append(labelRow, formattedValue, node("span", "comparison-metric__detail", detail));
    elements.comparisonMetrics.append(card);
  }

  function renderComparisonSummary(comparison, ipcSeries) {
    elements.comparisonSummary.hidden = false;
    elements.comparisonMetrics.replaceChildren();
    elements.comparisonPeriod.textContent = `Base común: ${formatMonth(comparison.baseMonth)} = 100 · ${formatMonth(comparison.baseMonth)} a ${formatMonth(comparison.endMonth)}.`;
    elements.ipcPublicationDate.textContent = formatDate(ipcSeries.source.updated_at, shortDate);
    comparisonMetric(
      "IPC general",
      "#667386",
      comparison.inflationChange,
      `Acumulado desde ${formatMonth(comparison.baseMonth)}`,
      true,
    );
    for (const series of comparison.eligible) {
      comparisonMetric(
        series.label,
        series.color,
        series.realChange,
        `Precio nominal ${formatChange(series.nominalChange)} · IPC ${formatChange(comparison.inflationChange)}`,
      );
    }
    const excludedNote = comparison.omitted.length
      ? ` Se omite ${comparison.omitted.join(", ")} por historia insuficiente (menos de seis meses con observaciones).`
      : "";
    elements.comparisonNote.textContent = `Cada precio es el promedio de las observaciones semanales disponibles en el mes; los meses sin observación no se interpolan.${excludedNote}`;
  }

  function chartColors() {
    const style = getComputedStyle(document.documentElement);
    return {
      grid: style.getPropertyValue("--line").trim() || "#dce3eb",
      muted: style.getPropertyValue("--muted").trim() || "#5f6d80",
    };
  }

  function renderInflationChart(seriesList) {
    elements.chartHeading.textContent = "Variación acumulada · base 100";
    elements.chartModeHint.textContent = "Índice común (100 = mes base) · precios mensuales e IPC mensual.";
    elements.detailSeriesLegend.setAttribute("aria-label", "Leyenda de puntos de monitoreo e IPC general");
    if (!seriesList.length) {
      elements.comparisonSummary.hidden = true;
      elements.detailChartNote.textContent = "Selecciona al menos un punto de monitoreo para comparar su evolución con el IPC.";
      elements.detailPeriodNote.textContent = "Sin puntos seleccionados";
      elements.detailChartSummary.textContent = "No hay puntos de monitoreo seleccionados.";
      renderSeriesLegend([]);
      return;
    }
    if (!currentIpcSeries) {
      elements.comparisonSummary.hidden = true;
      elements.detailChartNote.textContent = "Cargando la serie mensual de IPC…";
      return;
    }

    const comparison = buildInflationComparison(seriesList, currentIpcSeries);
    if (comparison.reason) {
      elements.comparisonSummary.hidden = true;
      elements.detailChartNote.textContent = comparison.reason;
      elements.detailPeriodNote.textContent = `IPC disponible hasta ${formatMonth(currentIpcSeries.source.latest_month)}`;
      elements.detailChartSummary.textContent = comparison.reason;
      elements.chart.setAttribute("aria-label", "Comparación con IPC no disponible para esta selección");
      renderSeriesLegend(comparison.eligible.map((series) => ({ ...series, symbol: detailSeriesSymbol })));
      const message = node("p", "chart-fallback", comparison.reason);
      message.id = "chart-status";
      elements.chart.parentElement.append(message);
      return;
    }

    renderComparisonSummary(comparison, currentIpcSeries);
    const ipcLegendColor = "#667386";
    const legendSeries = [
      ...comparison.eligible,
      { label: "IPC general", color: ipcLegendColor, legendType: "line", symbol: "" },
    ];
    renderSeriesLegend(legendSeries);
    elements.detailChartNote.textContent = `${comparison.eligible.length} ${comparison.eligible.length === 1 ? "punto de monitoreo" : "puntos de monitoreo"} · precio mensual frente al IPC general.`;
    elements.detailPeriodNote.textContent = `${formatMonth(comparison.baseMonth)} – ${formatMonth(comparison.endMonth)}`;
    elements.detailChartSummary.textContent = `Gráfico de índices con base 100 en ${formatMonth(comparison.baseMonth)}. Compara ${comparison.eligible.map((series) => series.label).join(", ")} con el IPC general, desde ${formatMonth(comparison.baseMonth)} hasta ${formatMonth(comparison.endMonth)}. Los precios son promedios de observaciones semanales agrupadas por mes.`;
    elements.chart.setAttribute("aria-label", `Variación acumulada de precios frente al IPC general, base ${formatMonth(comparison.baseMonth)} igual a 100`);
    if (!window.Chart) {
      const message = node("p", "chart-fallback", "El gráfico no está disponible; el resumen muestra la variación para el período común.");
      message.id = "chart-status";
      elements.chart.parentElement.append(message);
      return;
    }

    const colors = chartColors();
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const labels = comparison.months.map(formatMonth);
    const makeDataset = (series, data, kind, prices = null, basePrice = null) => {
      const firstIndex = data.findIndex((value) => Number.isFinite(value));
      const lastIndex = data.reduce((last, value, index) => Number.isFinite(value) ? index : last, -1);
      return {
        label: series.label,
        data,
        kind,
        prices,
        basePrice,
        firstIndex,
        lastIndex,
        borderColor: series.color,
        backgroundColor: series.color,
        borderWidth: kind === "ipc" ? 2.5 : 2,
        borderDash: kind === "ipc" ? [7, 5] : [],
        pointStyle: "circle",
        pointRadius: (context) => context.dataIndex === context.dataset.firstIndex || context.dataIndex === context.dataset.lastIndex ? 3 : 0,
        pointHoverRadius: 4,
        pointHitRadius: 12,
        pointBackgroundColor: series.color,
        pointBorderColor: "#ffffff",
        pointBorderWidth: 1,
        spanGaps: false,
        fill: false,
        tension: 0.12,
      };
    };
    const datasets = comparison.eligible.map((series) => makeDataset(
      series,
      series.data,
      "price",
      comparison.months.map((month) => series.monthlyPrices.get(month) ?? null),
      series.basePrice,
    ));
    datasets.push(makeDataset(
      { label: "IPC general", color: ipcLegendColor },
      comparison.ipcData,
      "ipc",
    ));
    const hoverGuide = {
      id: "detail-hover-guide",
      afterDraw(chart) {
        const active = chart.tooltip?.getActiveElements?.() || [];
        if (!active.length) return;
        const x = active[0].element.x;
        const { top, bottom } = chart.chartArea;
        const context = chart.ctx;
        context.save();
        context.beginPath();
        context.setLineDash([3, 4]);
        context.strokeStyle = "#8794a6";
        context.lineWidth = 1;
        context.moveTo(x, top);
        context.lineTo(x, bottom);
        context.stroke();
        context.restore();
      },
    };

    activeChart = new window.Chart(elements.chart, {
      type: "line",
      data: { labels, datasets },
      plugins: [hoverGuide],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: reducedMotion ? false : { duration: 180 },
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: (item) => Number.isFinite(item.parsed.y),
            itemSort: (left, right) => right.parsed.y - left.parsed.y,
            callbacks: {
              title: (items) => comparison.months[items[0]?.dataIndex]
                ? formatMonth(comparison.months[items[0].dataIndex])
                : "Mes",
              label: (context) => {
                const month = comparison.months[context.dataIndex];
                const indexChange = context.parsed.y - 100;
                if (context.dataset.kind === "ipc") {
                  return `IPC general — índice ${indexNumber.format(context.parsed.y)} (${formatChange(indexChange)} desde la base)`;
                }
                const price = context.dataset.prices[context.dataIndex];
                const monthIpc = currentIpcSeries.byMonth.get(month);
                const baseIpc = currentIpcSeries.byMonth.get(comparison.baseMonth);
                const realChange = ((price / context.dataset.basePrice) / (monthIpc / baseIpc) - 1) * 100;
                return `${context.dataset.label} — índice ${indexNumber.format(context.parsed.y)} · ${formatPrice(price)} · real ${formatChange(realChange)}`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: colors.muted, maxTicksLimit: 8, maxRotation: 0, autoSkip: true },
            border: { color: colors.grid },
          },
          y: {
            beginAtZero: false,
            title: { display: true, text: "Índice (base 100)", color: colors.muted, font: { size: 11, weight: "500" } },
            grid: { color: colors.grid },
            ticks: { color: colors.muted, callback: (value) => indexNumber.format(value) },
            border: { display: false },
          },
        },
      },
    });
  }

  function renderChart(seriesList) {
    if (activeChart) {
      activeChart.destroy();
      activeChart = null;
    }
    const chartStatus = byId("chart-status");
    if (chartStatus) chartStatus.remove();
    updateRangeShortcuts(seriesList);
    if (detailChartMode === "inflation") {
      renderInflationChart(seriesList);
      return;
    }
    elements.comparisonSummary.hidden = true;
    elements.chartHeading.textContent = "Promedio semanal";
    elements.chartModeHint.textContent = "Precios promedio semanales en pesos chilenos.";
    elements.detailSeriesLegend.setAttribute("aria-label", "Leyenda de puntos de monitoreo");
    const rangedSeries = seriesForSelectedRange(seriesList);
    renderSeriesLegend(rangedSeries);
    const dates = [...new Set(rangedSeries.flatMap((series) => series.points.map((point) => point.week_start)))].sort();
    const regionLabel = elements.detailRegion.options[elements.detailRegion.selectedIndex]?.text || "Nacional";
    const rangeLabel = detailRange === "1y" ? "último año" : detailRange === "5y" ? "últimos cinco años" : "toda la historia disponible";
    const firstDate = dates[0];
    const lastDate = dates.at(-1);
    elements.detailChartNote.textContent = rangedSeries.length
      ? `${rangedSeries.length} ${rangedSeries.length === 1 ? "punto con datos" : "puntos con datos"} · ${regionLabel} · promedio semanal en pesos chilenos.`
      : "Selecciona puntos de monitoreo para comparar su evolución semanal.";
    elements.detailPeriodNote.textContent = firstDate && lastDate
      ? `${formatDate(firstDate, shortDate)} – ${formatDate(lastDate, shortDate)}`
      : "Sin semanas disponibles para este período";
    elements.detailChartSummary.textContent = dates.length
      ? `Gráfico de líneas con ${rangedSeries.map((series) => series.label).join(", ")}, desde ${formatDate(firstDate, shortDate)} hasta ${formatDate(lastDate, shortDate)}. Valores de precio promedio semanal en pesos chilenos; período: ${rangeLabel}.`
      : "No hay datos disponibles para el gráfico en esta selección.";
    elements.chart.setAttribute("aria-label", dates.length
      ? `Gráfico comparativo de precios semanales: ${rangedSeries.map((series) => series.label).join(", ")}`
      : "Gráfico comparativo sin datos para la selección actual");
    if (!dates.length) return;
    if (!window.Chart) {
      const message = node("p", "chart-fallback", "El gráfico no está disponible; abre la tabla para consultar los datos.");
      message.id = "chart-status";
      elements.chart.parentElement.append(message);
      return;
    }

    const colors = chartColors();
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const labels = dates.map((date) => formatDate(date, shortDate));
    const datasets = rangedSeries.map((series) => {
      const pointsByDate = new Map(series.points.map((point) => [point.week_start, point]));
      const data = dates.map((date) => pointsByDate.get(date)?.average_clp ?? null);
      const firstIndex = data.findIndex((value) => Number.isFinite(value));
      const lastIndex = data.reduce((last, value, index) => Number.isFinite(value) ? index : last, -1);
      return {
        label: series.label,
        data,
        firstIndex,
        lastIndex,
        borderColor: series.color,
        backgroundColor: series.color,
        borderWidth: 2,
        pointStyle: series.marker,
        pointRadius: (context) => context.dataIndex === context.dataset.firstIndex || context.dataIndex === context.dataset.lastIndex ? 3 : 0,
        pointHoverRadius: 4,
        pointHitRadius: 12,
        pointBackgroundColor: series.color,
        pointBorderColor: "#ffffff",
        pointBorderWidth: 1,
        spanGaps: false,
        fill: false,
        tension: 0.12,
      };
    });
    const hoverGuide = {
      id: "detail-hover-guide",
      afterDraw(chart) {
        const active = chart.tooltip?.getActiveElements?.() || [];
        if (!active.length) return;
        const x = active[0].element.x;
        const { top, bottom } = chart.chartArea;
        const context = chart.ctx;
        context.save();
        context.beginPath();
        context.setLineDash([3, 4]);
        context.strokeStyle = "#8794a6";
        context.lineWidth = 1;
        context.moveTo(x, top);
        context.lineTo(x, bottom);
        context.stroke();
        context.restore();
      },
    };

    activeChart = new window.Chart(elements.chart, {
      type: "line",
      data: { labels, datasets },
      plugins: [hoverGuide],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: reducedMotion ? false : { duration: 180 },
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: (item) => Number.isFinite(item.parsed.y),
            itemSort: (left, right) => right.parsed.y - left.parsed.y,
            callbacks: {
              title: (items) => {
                const date = dates[items[0]?.dataIndex];
                return date ? formatDate(date, shortDate) : "Semana";
              },
              label: (context) => `${context.dataset.label} — ${formatPrice(context.parsed.y)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: colors.muted, maxTicksLimit: 8, maxRotation: 0, autoSkip: true },
            border: { color: colors.grid },
          },
          y: {
            beginAtZero: true,
            grid: { color: colors.grid },
            ticks: { color: colors.muted, callback: (value) => currency.format(value) },
            border: { display: false },
          },
        },
      },
    });
  }

  function renderHistoryTable(seriesList) {
    elements.historyRows.replaceChildren();
    const rows = seriesList.flatMap((series) => series.points.slice(-8).map((point) => ({ series, point })))
      .sort((left, right) => right.point.week_start.localeCompare(left.point.week_start)
        || left.series.label.localeCompare(right.series.label, "es-CL"));
    rows.forEach(({ series, point }, index) => {
      const row = document.createElement("tr");
      if (index === 0) row.classList.add("history-row--latest");
      const date = node("th", "history-date", formatDate(point.week_start, shortDate));
      date.scope = "row";
      const pointCell = node("td", "history-point");
      const swatch = node("span", "history-series-swatch");
      swatch.textContent = series.symbol;
      swatch.style.setProperty("--series-color", series.color);
      swatch.setAttribute("aria-hidden", "true");
      pointCell.append(swatch, node("span", "", series.label));
      row.append(
        date,
        pointCell,
        node("td", "history-number", formatPrice(point.minimum_clp)),
        node("td", "history-number history-number--average", formatPrice(point.average_clp)),
        node("td", "history-number", formatPrice(point.maximum_clp)),
      );
      elements.historyRows.append(row);
    });
    elements.historyPeriodLabel.textContent = rows.length
      ? `Últimas 8 semanas · ${seriesList.length} ${seriesList.length === 1 ? "punto seleccionado" : "puntos seleccionados"}`
      : "Sin semanas en esta selección";
  }

  function renderDetailSeries(seriesProduct) {
    const seriesList = selectedDetailSeries(seriesProduct).filter((series) => series.points.length);
    renderDetailSummary(seriesProduct, seriesList);
    renderChart(seriesList);
    renderHistoryTable(seriesList);
    if (seriesList.length) {
      clearStatus(elements.detailStatus);
    } else if (selectedDetailPointTypes.size === 0) {
      showStatus(elements.detailStatus, "Selecciona al menos un punto de monitoreo para ver el gráfico.");
    } else {
      showStatus(elements.detailStatus, "No hay semanas disponibles para esta selección. Prueba otra región o selecciona otros puntos de monitoreo.");
    }
  }

  function updateChartModeButtons() {
    for (const button of elements.chartModeSwitch.querySelectorAll("button[data-chart-mode]")) {
      button.setAttribute("aria-pressed", String(button.dataset.chartMode === detailChartMode));
    }
  }

  async function renderProductDetail(slug, retry = false, preferredPointType = "") {
    const requestId = ++detailRequestId;
    const found = findProduct(slug);
    if (!found) {
      showStatus(elements.detailStatus, "No encontramos ese alimento en los datos publicados.", { error: true });
      return;
    }
    currentProductSlug = slug;
    currentDetailSeriesProduct = null;
    selectedDetailPointTypes = new Set();
    detailRange = "max";
    detailChartMode = "nominal";
    updateChartModeButtons();
    elements.detail.hidden = false;
    elements.detailSeriesPicker.open = false;
    elements.historyDisclosure.open = false;
    elements.historyToggleLabel.textContent = "Ver datos en tabla";
    elements.detailRegion.replaceChildren(new Option("Nacional · regiones con datos", "national"));
    elements.detailGroup.textContent = found.group.group_name;
    const presentation = productPresentation(found.product);
    elements.detailTitle.textContent = presentation.name;
    elements.detailUnit.textContent = `Unidad de venta: ${found.product.unit}`;
    const aliases = (found.product.aliases || [])
      .map((alias) => productPresentation({ name: alias }).name)
      .filter((alias) => alias !== presentation.name);
    const detailNotes = [presentation.metadata, aliases.length ? `También publicado como: ${aliases.join("; ")}` : ""]
      .filter(Boolean);
    elements.detailAliases.hidden = detailNotes.length === 0;
    elements.detailAliases.textContent = detailNotes.join(" · ");
    elements.detailReferenceWeek.textContent = "Cargando…";
    elements.detailScopeRegion.textContent = "—";
    elements.detailPointsCount.textContent = "—";
    elements.detailPointsNote.textContent = "Con datos disponibles";
    elements.detailRangeValue.textContent = "—";
    elements.detailRangeNote.textContent = "Promedio por punto";
    elements.detailSeriesSummary.textContent = "Cargando…";
    elements.detailSeriesAvailability.textContent = "Cargando puntos de monitoreo…";
    elements.detailSeriesList.replaceChildren();
    elements.detailChartNote.textContent = "Compara los precios promedio semanales por punto de monitoreo.";
    elements.detailPeriodNote.textContent = "Cargando historial semanal…";
    elements.detailChartSummary.textContent = "Cargando el historial semanal del producto.";
    renderChart([]);
    elements.historyRows.replaceChildren();
    elements.historyPeriodLabel.textContent = "Cargando semanas recientes…";
    showStatus(elements.detailStatus, retry ? "Volviendo a cargar la historia…" : "Cargando la historia semanal…");
    try {
      const groupSeries = await loadGroupSeries(found.group);
      if (requestId !== detailRequestId || currentProductSlug !== slug) return;
      const seriesProduct = (groupSeries.products || {})[slug];
      if (!seriesProduct) throw new Error("Este producto no tiene un archivo de historia disponible.");
      populateDetailRegions(seriesProduct);
      populateDetailPointTypes(seriesProduct, preferredPointType);
      currentDetailSeriesProduct = seriesProduct;
      renderDetailSeries(seriesProduct);
    } catch (error) {
      if (requestId !== detailRequestId || currentProductSlug !== slug) return;
      showStatus(elements.detailStatus, error.message || "No se pudo cargar la historia del producto.", {
        error: true,
        retryLabel: "Reintentar carga",
        retry: () => {
          seriesCache.delete(found.group.slug);
          renderProductDetail(slug, true, preferredPointType);
        },
      });
    }
  }

  function renderRoute() {
    if (!indexData) return;
    const match = window.location.hash.match(/^#\/producto\/([^?]+)(?:\?(.*))?$/);
    const isCatalog = /^#\/productos(?:\/|$)/.test(window.location.hash);
    const isDetail = Boolean(match);
    const isHome = !isCatalog && !isDetail;
    document.body.classList.toggle("catalog-route", isCatalog);
    elements.pageHero.hidden = isDetail;
    elements.scopeControls.hidden = isDetail;
    elements.pageTitle.textContent = isCatalog ? "Todos los productos" : "Precios de alimentos en Chile";
    elements.pageLede.textContent = isCatalog
      ? "Consulta precios de referencia y su variación para los alimentos con datos disponibles."
      : "Consulta precios de referencia y su evolución semanal en supermercados y otros puntos de monitoreo.";
    elements.homeMetadata.hidden = isCatalog;
    elements.headerNavLink.href = isHome ? "#/productos" : "#";
    elements.headerNavLink.replaceChildren(
      document.createTextNode(isHome ? "Todos los productos " : "Resumen semanal "),
      node("span", "", "→"),
    );
    elements.scopeControls.classList.toggle("controls--catalog", isCatalog);
    elements.catalogPage.hidden = !isCatalog;
    if (!isCatalog) elements.catalogPointPicker.open = false;
    elements.dashboard.hidden = isCatalog || isDetail;
    elements.detail.hidden = !isDetail;
    if (match) {
      let slug;
      try {
        slug = decodeURIComponent(match[1]);
      } catch (_error) {
        slug = match[1];
      }
      const routeParameters = new URLSearchParams(match[2] || "");
      renderProductDetail(slug, false, routeParameters.get("point") || "");
      return;
    }
    detailRequestId += 1;
    currentProductSlug = null;
    currentDetailSeriesProduct = null;
    selectedDetailPointTypes = new Set();
    if (activeChart) {
      activeChart.destroy();
      activeChart = null;
    }
    elements.detail.hidden = true;
    clearStatus(elements.detailStatus);
    if (isCatalog) renderIndex();
    else if (isHome) renderDashboard();
  }

  async function loadIndex(retry = false) {
    showStatus(elements.appStatus, retry ? "Actualizando el índice…" : "Cargando precios de ODEPA…");
    try {
      const response = await fetch(new URL("index.json", DATA_ROOT), {
        cache: "no-cache",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`No se pudo cargar el índice (HTTP ${response.status}).`);
      const document = await response.json();
      if (document.schema_version !== 1 || !Array.isArray(document.groups)) {
        throw new Error("El índice tiene un formato que esta página no reconoce.");
      }
      indexData = document;
      populateFilters();
      updateSourceStamp();
      clearStatus(elements.appStatus);
      renderRoute();
    } catch (error) {
      showStatus(elements.appStatus, error.message || "No se pudieron cargar los precios publicados.", {
        error: true,
        retryLabel: "Volver a intentar",
        retry: () => loadIndex(true),
      });
    }
  }

  elements.search.addEventListener("input", () => {
    catalogPageNumber = 1;
    renderIndex();
  });
  elements.catalogSort.addEventListener("change", () => {
    catalogPageNumber = 1;
    renderIndex();
  });
  elements.clearSearch.addEventListener("click", () => {
    elements.search.value = "";
    catalogPageNumber = 1;
    renderIndex();
    elements.search.focus();
  });
  elements.recentOnly.addEventListener("change", () => {
    catalogPageNumber = 1;
    updateFreshnessNote();
    renderIndex();
  });
  elements.regionFilter.addEventListener("change", () => {
    catalogPageNumber = 1;
    renderIndex();
    renderDashboard();
  });
  elements.catalogPointOptions.addEventListener("change", (event) => {
    const input = event.target.closest('input[type="checkbox"]');
    if (!input) return;
    if (input.checked) selectedCatalogPointTypes.add(input.value);
    else selectedCatalogPointTypes.delete(input.value);
    catalogPageNumber = 1;
    updateCatalogPointPicker();
    renderIndex();
  });
  elements.catalogPointsSelectAll.addEventListener("click", () => {
    selectedCatalogPointTypes = new Set((indexData.point_types || []).map(({ slug }) => slug));
    catalogPageNumber = 1;
    populateCatalogPointPicker();
    renderIndex();
  });
  elements.catalogPointsClear.addEventListener("click", () => {
    selectedCatalogPointTypes.clear();
    catalogPageNumber = 1;
    populateCatalogPointPicker();
    renderIndex();
  });
  elements.pointFilter.addEventListener("change", () => {
    catalogPageNumber = 1;
    renderIndex();
    renderDashboard();
  });
  elements.detailRegion.addEventListener("change", () => {
    if (currentDetailSeriesProduct) renderDetailSeries(currentDetailSeriesProduct);
  });
  elements.chartModeSwitch.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-chart-mode]");
    if (!button || button.dataset.chartMode === detailChartMode) return;
    detailChartMode = button.dataset.chartMode;
    updateChartModeButtons();
    if (detailChartMode !== "inflation") {
      if (currentDetailSeriesProduct) renderDetailSeries(currentDetailSeriesProduct);
      return;
    }
    if (currentDetailSeriesProduct) renderDetailSeries(currentDetailSeriesProduct);
    try {
      currentIpcSeries = await loadIpcSeries();
      if (detailChartMode === "inflation" && currentDetailSeriesProduct) {
        renderDetailSeries(currentDetailSeriesProduct);
      }
    } catch (error) {
      detailChartMode = "nominal";
      updateChartModeButtons();
      if (currentDetailSeriesProduct) renderDetailSeries(currentDetailSeriesProduct);
      const message = node("p", "chart-fallback", error.message || "No se pudo cargar el IPC.");
      message.id = "chart-status";
      elements.chart.parentElement.append(message);
    }
  });
  elements.detailSeriesList.addEventListener("change", (event) => {
    const input = event.target.closest('input[type="checkbox"]');
    if (!input || !currentDetailSeriesProduct) return;
    if (input.checked) selectedDetailPointTypes.add(input.value);
    else selectedDetailPointTypes.delete(input.value);
    updateDetailSeriesPicker(currentDetailSeriesProduct);
    renderDetailSeries(currentDetailSeriesProduct);
  });
  elements.detailRangeShortcuts.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-detail-range]");
    if (!button || button.disabled || !currentDetailSeriesProduct) return;
    detailRange = button.dataset.detailRange;
    renderDetailSeries(currentDetailSeriesProduct);
  });
  elements.historyDisclosure.addEventListener("toggle", () => {
    elements.historyToggleLabel.textContent = elements.historyDisclosure.open ? "Ocultar tabla" : "Ver datos en tabla";
  });
  document.addEventListener("click", (event) => {
    if (elements.detailSeriesPicker.open && !elements.detailSeriesPicker.contains(event.target)) {
      elements.detailSeriesPicker.open = false;
    }
    if (elements.catalogPointPicker.open && !elements.catalogPointPicker.contains(event.target)) {
      elements.catalogPointPicker.open = false;
    }
  });
  elements.catalogPointPicker.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && elements.catalogPointPicker.open) {
      event.preventDefault();
      elements.catalogPointPicker.open = false;
      elements.catalogPointPicker.querySelector("summary")?.focus();
    }
  });
  elements.detailSeriesPicker.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && elements.detailSeriesPicker.open) {
      event.preventDefault();
      elements.detailSeriesPicker.open = false;
      elements.detailSeriesPicker.querySelector("summary")?.focus();
    }
  });
  elements.openInterpretation.addEventListener("click", () => openInfoDrawer("interpretation"));
  elements.openDataNotes.addEventListener("click", () => openInfoDrawer("notes"));
  elements.closeInfoDrawer.addEventListener("click", () => elements.infoDrawer.close());
  elements.infoDrawer.addEventListener("click", (event) => {
    if (event.target === elements.infoDrawer) elements.infoDrawer.close();
  });
  elements.back.addEventListener("click", () => {
    window.location.hash = "#/productos";
  });
  window.addEventListener("hashchange", renderRoute);

  loadIndex();
})();
