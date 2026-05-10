const runButton = document.getElementById('run-scan');
const spinner = document.getElementById('scan-spinner');
const statusText = document.getElementById('scan-status');
const thresholdInput = document.getElementById('threshold');
const resultsBody = document.getElementById('results-body');
const resultCount = document.getElementById('result-count');
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

let currentResults = [];
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

function renderRows(results) {
  const sortedResults = sortResults(results);
  resultCount.textContent = `${sortedResults.length} result${sortedResults.length === 1 ? '' : 's'}`;
  updateSortIndicators();

  if (sortedResults.length === 0) {
    resultsBody.innerHTML = '<tr><td colspan="9" class="text-center text-secondary py-4">No matching signals found.</td></tr>';
    return;
  }

  resultsBody.innerHTML = sortedResults.map((row) => `
    <tr>
      <td class="fw-semibold">${escapeHtml(row.ticker)}</td>
      <td>${row.company_name ? escapeHtml(row.company_name) : '—'}</td>
      <td>${formatMarketCap(row.market_cap)}</td>
      <td>${boolBadge(row.near_earnings)}</td>
      <td>${boolBadge(row.near_yearly)}</td>
      <td>${formatNumber(row.distance_score)}</td>
      <td>${formatNumber(row.min_distance_earnings)}</td>
      <td>${formatNumber(row.min_distance_yearly)}</td>
      <td>$${formatNumber(row.last_price, 2)}</td>
    </tr>
  `).join('');
}

function handleSortClick(event) {
  const nextKey = event.currentTarget.dataset.sortKey;
  currentSort = {
    key: nextKey,
    direction: currentSort.key === nextKey && currentSort.direction === 'asc' ? 'desc' : 'asc',
  };
  renderRows(currentResults);
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
    renderRows(currentResults);
    statusText.textContent = `Completed at ${new Date().toLocaleTimeString()}.`;
  } catch (error) {
    currentResults = [];
    resultsBody.innerHTML = `<tr><td colspan="9" class="text-danger text-center py-4">${escapeHtml(error.message)}</td></tr>`;
    statusText.textContent = 'Scan failed.';
  } finally {
    spinner.classList.add('d-none');
    runButton.disabled = false;
  }
}

sortButtons.forEach((button) => button.addEventListener('click', handleSortClick));
runButton.addEventListener('click', runScan);
updateSortIndicators();
