const runButton = document.getElementById('run-scan');
const spinner = document.getElementById('scan-spinner');
const statusText = document.getElementById('scan-status');
const thresholdInput = document.getElementById('threshold');
const resultsBody = document.getElementById('results-body');
const resultCount = document.getElementById('result-count');

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return Number(value).toFixed(digits);
}

function boolBadge(value) {
  const classes = value ? 'text-bg-success' : 'text-bg-secondary';
  const label = value ? 'Yes' : 'No';
  return `<span class="badge ${classes}">${label}</span>`;
}

function renderRows(results) {
  resultCount.textContent = `${results.length} result${results.length === 1 ? '' : 's'}`;

  if (results.length === 0) {
    resultsBody.innerHTML = '<tr><td colspan="7" class="text-center text-secondary py-4">No matching signals found.</td></tr>';
    return;
  }

  resultsBody.innerHTML = results.map((row) => `
    <tr>
      <td class="fw-semibold">${row.ticker}</td>
      <td>${boolBadge(row.near_earnings)}</td>
      <td>${boolBadge(row.near_yearly)}</td>
      <td>${formatNumber(row.distance_score)}</td>
      <td>${formatNumber(row.min_distance_earnings)}</td>
      <td>${formatNumber(row.min_distance_yearly)}</td>
      <td>$${formatNumber(row.last_price, 2)}</td>
    </tr>
  `).join('');
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
    renderRows(payload.results || []);
    statusText.textContent = `Completed at ${new Date().toLocaleTimeString()}.`;
  } catch (error) {
    resultsBody.innerHTML = `<tr><td colspan="7" class="text-danger text-center py-4">${error.message}</td></tr>`;
    statusText.textContent = 'Scan failed.';
  } finally {
    spinner.classList.add('d-none');
    runButton.disabled = false;
  }
}

runButton.addEventListener('click', runScan);
