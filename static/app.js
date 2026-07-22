// Game Picker Frontend

const form = document.getElementById('preferences-form');
const inputSection = document.getElementById('input-section');
const traceSection = document.getElementById('trace-section');
const traceContainer = document.getElementById('trace-container');
const resultsSection = document.getElementById('results-section');
const resultsContainer = document.getElementById('results-container');
const submitBtn = document.getElementById('submit-btn');
const resetBtn = document.getElementById('reset-btn');

const promptInput = document.getElementById('pref-prompt');
const genreSelect = document.getElementById('pref-genre');
const budgetSelect = document.getElementById('pref-budget');
const platformSelect = document.getElementById('pref-platform');
const vibeSelect = document.getElementById('pref-vibe');

// ---- Form Submit ----

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  const prompt = promptInput.value.trim();
  if (!prompt) {
    promptInput.focus();
    return;
  }

  // Hints are optional: only include the ones the user explicitly set.
  const hints = {};
  if (genreSelect.value) hints.genre = genreSelect.value;
  if (budgetSelect.value) hints.budget = budgetSelect.value;
  if (platformSelect.value) hints.platform = platformSelect.value;
  if (vibeSelect.value) hints.vibe = vibeSelect.value;

  startRun({ prompt, hints });
});

resetBtn.addEventListener('click', () => {
  inputSection.classList.remove('dimmed');
  traceSection.hidden = true;
  resultsSection.hidden = true;
  resetBtn.hidden = true;
  traceContainer.innerHTML = '';
  resultsContainer.innerHTML = '';
  submitBtn.disabled = false;
  submitBtn.classList.remove('loading');
});

// ---- Run Agent ----

async function startRun(prefs) {
  submitBtn.disabled = true;
  submitBtn.classList.add('loading');
  inputSection.classList.add('dimmed');

  traceSection.hidden = false;
  resultsSection.hidden = true;
  resultsContainer.innerHTML = '';
  resetBtn.hidden = true;
  traceContainer.innerHTML = '';

  try {
    const response = await fetch('/api/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(prefs),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event = JSON.parse(line.slice(6));
            handleEvent(event);
          } catch (err) { /* skip malformed */ }
        }
      }
    }

    if (buffer.startsWith('data: ')) {
      try { handleEvent(JSON.parse(buffer.slice(6))); } catch (err) { /* skip */ }
    }
  } catch (err) {
    resultsSection.hidden = false;
    resultsContainer.innerHTML = '<p style="color:var(--red)">Connection error: ' + escapeHtml(err.message) + '</p>';
    resetBtn.hidden = false;
  }

  submitBtn.disabled = false;
  submitBtn.classList.remove('loading');
}

// ---- Event Handlers ----
// Each event from the agentic loop is rendered live so the user can watch
// the Observe -> Think -> Act -> Loop cycle as it happens.

function handleEvent(event) {
  switch (event.type) {
    case 'iteration_start':
      addTrace('loop', 'Loop iteration ' + event.iteration, 'Observe -> Think -> Act');
      break;

    case 'thinking':
      if (event.text && event.text.trim()) {
        addTrace('think', 'Reasoning', event.text.trim());
      }
      break;

    case 'tool_call':
      addTrace('act', 'Tool call: ' + event.name, formatToolInput(event.input));
      break;

    case 'tool_result':
      addTrace('observe', 'Result from ' + event.name, event.preview, true);
      break;

    case 'answer':
      showResults(event.text);
      break;

    case 'run_summary':
      addTrace(
        'done',
        'Run summary',
        'Iterations: ' + event.iterations + '\n' +
        'Tools called: ' + (event.tool_calls.length ? event.tool_calls.join(' -> ') : 'none'),
        true
      );
      break;

    case 'done':
      addTrace('done', 'Agent finished', 'Completed in ' + event.iterations + ' loop iteration(s)');
      resetBtn.hidden = false;
      break;

    case 'error':
      resultsSection.hidden = false;
      resultsContainer.innerHTML = '<p style="color:var(--red)">Error: ' + escapeHtml(event.message) + '</p>';
      resetBtn.hidden = false;
      break;

    default:
      break;
  }
}

// ---- Trace Rendering ----

function addTrace(kind, title, body, mono) {
  const step = document.createElement('div');
  step.className = 'trace-step trace-' + kind;

  const head = document.createElement('div');
  head.className = 'trace-head';
  head.textContent = title;
  step.appendChild(head);

  if (body) {
    const detail = document.createElement('div');
    detail.className = mono ? 'trace-body trace-body-mono' : 'trace-body';
    detail.textContent = body;
    step.appendChild(detail);
  }

  traceContainer.appendChild(step);
  step.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function formatToolInput(input) {
  try {
    return JSON.stringify(input, null, 2);
  } catch (err) {
    return String(input);
  }
}

// ---- Render ----

function showResults(text) {
  resultsSection.hidden = false;
  resultsContainer.innerHTML = renderMarkdown(cleanDashes(text));
  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---- Utilities ----

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function cleanDashes(text) {
  // Remove em dashes surrounded by spaces
  return text.replace(/ — /g, ' ').replace(/ —/g, ' ').replace(/— /g, ' ');
}

function renderMarkdown(text) {
  const lines = text.split('\n');
  let html = '';
  let inList = false;
  let inTable = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      if (inList) { html += '</ul>'; inList = false; }
      if (inTable) { html += '</tbody></table>'; inTable = false; }
      html += '<hr>';
      continue;
    }

    // Table
    if (line.includes('|') && line.trim().startsWith('|')) {
      const cells = line.split('|').filter(c => c.trim() !== '');
      if (!inTable) {
        const nextLine = lines[i + 1] || '';
        if (nextLine.includes('---')) {
          html += '<table><thead><tr>';
          cells.forEach(c => { html += '<th>' + formatCell(c.trim()) + '</th>'; });
          html += '</tr></thead><tbody>';
          inTable = true;
          i++;
          continue;
        }
      }
      if (inTable) {
        html += '<tr>';
        cells.forEach(c => { html += '<td>' + formatCell(c.trim()) + '</td>'; });
        html += '</tr>';
        continue;
      }
    } else if (inTable) {
      html += '</tbody></table>';
      inTable = false;
    }

    // Headers
    if (line.startsWith('### ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<h3>' + formatCell(line.slice(4)) + '</h3>';
      continue;
    }
    if (line.startsWith('## ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<h2>' + formatCell(line.slice(3)) + '</h2>';
      continue;
    }
    if (line.startsWith('# ')) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<h1>' + formatCell(line.slice(2)) + '</h1>';
      continue;
    }
    if (/^=+$/.test(line.trim())) continue;

    // List items
    if (/^[\s]*[-*] /.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += '<li>' + formatCell(line.replace(/^[\s]*[-*] /, '')) + '</li>';
      continue;
    } else if (inList) {
      html += '</ul>';
      inList = false;
    }

    // Empty line
    if (line.trim() === '') {
      html += '<br>';
      continue;
    }

    // Regular text
    html += '<p>' + formatCell(line) + '</p>';
  }

  if (inList) html += '</ul>';
  if (inTable) html += '</tbody></table>';

  return html;
}

function formatCell(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/(\d+)\/(\d+)/g, '<span class="score-num">$1/$2</span>');
}
