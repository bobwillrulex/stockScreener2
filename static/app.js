const runButton = document.getElementById('run-scan');
const spinner = document.getElementById('scan-spinner');
const statusText = document.getElementById('scan-status');
const thresholdInput = document.getElementById('threshold');
const resultsBody = document.getElementById('results-body');
const resultCount = document.getElementById('result-count');
const databaseStatus = document.getElementById('database-status');
const newTickerCount = document.getElementById('new-ticker-count');
const tableTitle = document.getElementById('table-title');
const viewButtons = document.querySelectorAll('[data-result-view]');
const sortButtons = document.querySelectorAll('[data-sort-key]');

const columnTypes = {
  ticker: 'text',
  company_name: 'text',
  market_cap: 'number',
  near_earnings: 'boolean',
  near_yearly: 'boolean',
  distance_score: 'number',
  min_distance_earnings: 'number',
  min_distance_yearly: 'number',
  last_price: 'number',
};

const emptyMessages = {
  signals: 'No matching signals found.',
  new: 'No new tickers found compared with the previous scan.',
};

let currentResults = [];
let currentNewTickerResults = [];
let currentView = 'signals';
let currentSort = { key: 'market_cap', direction: 'desc' };

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return Number(value).toFixed(digits);
}

function formatMarketCap(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }

  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function boolBadge(value) {
  const classes = value ? 'text-bg-success' : 'text-bg-secondary';
  const label = value ? 'Yes' : 'No';
  return `<span class="badge ${classes}">${label}</span>`;
}

function tradingViewUrlForTicker(ticker) {
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(String(ticker).trim().toUpperCase())}`;
}

function normalizeSortValue(row, key) {
  const value = row[key];
  if (value === null || value === undefined || value === '') {
    return null;
  }

  if (columnTypes[key] === 'text') {
    return String(value).toLocaleLowerCase();
  }

  if (columnTypes[key] === 'boolean') {
    return value ? 1 : 0;
  }

  const numberValue = Number(value);
  return Number.isNaN(numberValue) ? null : numberValue;
}

function sortResults(results) {
  const directionMultiplier = currentSort.direction === 'asc' ? 1 : -1;

  return [...results].sort((left, right) => {
    const leftValue = normalizeSortValue(left, currentSort.key);
    const rightValue = normalizeSortValue(right, currentSort.key);

    if (leftValue === null && rightValue === null) {
      return String(left.ticker).localeCompare(String(right.ticker));
    }
    if (leftValue === null) {
      return 1;
    }
    if (rightValue === null) {
      return -1;
    }

    if (columnTypes[currentSort.key] === 'text') {
      const comparison = leftValue.localeCompare(rightValue);
      return comparison === 0
        ? String(left.ticker).localeCompare(String(right.ticker))
        : comparison * directionMultiplier;
    }

    const comparison = leftValue - rightValue;
    return comparison === 0
      ? String(left.ticker).localeCompare(String(right.ticker))
      : comparison * directionMultiplier;
  });
}

function updateSortIndicators() {
  sortButtons.forEach((button) => {
    const indicator = button.querySelector('.sort-indicator');
    const isActive = button.dataset.sortKey === currentSort.key;
    button.setAttribute(
      'aria-sort',
      isActive ? (currentSort.direction === 'asc' ? 'ascending' : 'descending') : 'none',
    );
    indicator.textContent = isActive ? (currentSort.direction === 'asc' ? '▲' : '▼') : '';
  });
}

function activeResults() {
  return currentView === 'new' ? currentNewTickerResults : currentResults;
}

function updateViewButtons() {
  viewButtons.forEach((button) => {
    const isActive = button.dataset.resultView === currentView;
    button.classList.toggle('btn-primary', isActive);
    button.classList.toggle('btn-outline-primary', !isActive);
    button.setAttribute('aria-pressed', String(isActive));
  });
}

function renderRows(results = activeResults()) {
  const sortedResults = sortResults(results);
  const isNewTickerView = currentView === 'new';
  const itemLabel = isNewTickerView ? 'new ticker' : 'result';

  tableTitle.textContent = isNewTickerView ? 'New Tickers' : 'Signals';
  resultCount.textContent = `${sortedResults.length} ${itemLabel}${sortedResults.length === 1 ? '' : 's'}`;
  updateSortIndicators();
  updateViewButtons();

  if (sortedResults.length === 0) {
    resultsBody.innerHTML = `<tr><td colspan="9" class="text-center text-secondary py-4">${emptyMessages[currentView]}</td></tr>`;
    return;
  }

  resultsBody.innerHTML = sortedResults.map((row) => {
    const ticker = String(row.ticker || '').trim();
    const tradingViewUrl = tradingViewUrlForTicker(ticker);

    return `
    <tr class="ticker-row" tabindex="0" role="link" data-trading-view-url="${tradingViewUrl}" aria-label="Open ${escapeHtml(ticker)} on TradingView" title="Open ${escapeHtml(ticker)} on TradingView">
      <td class="fw-semibold">${escapeHtml(ticker)}</td>
      <td>${row.company_name ? escapeHtml(row.company_name) : '—'}</td>
      <td>${formatMarketCap(row.market_cap)}</td>
      <td>${boolBadge(row.near_earnings)}</td>
      <td>${boolBadge(row.near_yearly)}</td>
      <td>${formatNumber(row.distance_score)}</td>
      <td>${formatNumber(row.min_distance_earnings)}</td>
      <td>${formatNumber(row.min_distance_yearly)}</td>
      <td>$${formatNumber(row.last_price, 2)}</td>
    </tr>
  `;
  }).join('');
}

function renderScanDatabase(scanDatabase) {
  if (!scanDatabase) {
    currentNewTickerResults = [];
    databaseStatus.textContent = 'Scan database status was not returned.';
    newTickerCount.textContent = '0 new tickers';
    renderRows();
    return;
  }

  currentNewTickerResults = scanDatabase.new_results || [];
  const tickers = scanDatabase.new_tickers || [];
  databaseStatus.textContent = scanDatabase.message || 'Scan database updated.';
  newTickerCount.textContent = `${tickers.length} new ticker${tickers.length === 1 ? '' : 's'}`;
  renderRows();
}

function handleSortClick(event) {
  const nextKey = event.currentTarget.dataset.sortKey;
  currentSort = {
    key: nextKey,
    direction: currentSort.key === nextKey && currentSort.direction === 'asc' ? 'desc' : 'asc',
  };
  renderRows();
}

function handleViewClick(event) {
  currentView = event.currentTarget.dataset.resultView;
  renderRows();
}

function openTradingViewRow(row) {
  const tradingViewUrl = row.dataset.tradingViewUrl;
  if (tradingViewUrl) {
    window.location.href = tradingViewUrl;
  }
}

function handleResultsClick(event) {
  const row = event.target.closest('.ticker-row');
  if (row) {
    openTradingViewRow(row);
  }
}

function handleResultsKeydown(event) {
  if (event.key !== 'Enter' && event.key !== ' ') {
    return;
  }

  const row = event.target.closest('.ticker-row');
  if (row) {
    event.preventDefault();
    openTradingViewRow(row);
  }
}

async function runScan() {
  runButton.disabled = true;
  spinner.classList.remove('d-none');
  statusText.textContent = 'Scanning Russell 1000 constituents. This can take several minutes...';

  try {
    const response = await fetch('/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ threshold: Number(thresholdInput.value || 0.1) }),
    });

    if (!response.ok) {
      throw new Error(`Scan failed with HTTP ${response.status}`);
    }

    const payload = await response.json();
    currentResults = payload.results || [];
    currentSort = { key: 'market_cap', direction: 'desc' };
    renderScanDatabase(payload.scan_database);
    statusText.textContent = `Completed at ${new Date().toLocaleTimeString()}.`;
  } catch (error) {
    currentResults = [];
    currentNewTickerResults = [];
    resultsBody.innerHTML = `<tr><td colspan="9" class="text-danger text-center py-4">${escapeHtml(error.message)}</td></tr>`;
    databaseStatus.textContent = 'Scan database was not updated.';
    newTickerCount.textContent = '0 new tickers';
    statusText.textContent = 'Scan failed.';
  } finally {
    spinner.classList.add('d-none');
    runButton.disabled = false;
  }
}

sortButtons.forEach((button) => button.addEventListener('click', handleSortClick));
viewButtons.forEach((button) => button.addEventListener('click', handleViewClick));
resultsBody.addEventListener('click', handleResultsClick);
resultsBody.addEventListener('keydown', handleResultsKeydown);
runButton.addEventListener('click', runScan);
renderRows();
