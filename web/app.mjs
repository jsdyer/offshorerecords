import {countryRows, countrySource, matchedReview, relationshipDates, roles, selectedValues, totalRecords} from './model.mjs';

const get = id => document.getElementById(id);
const format = new Intl.NumberFormat('en-CA');
const count = value => Number.isInteger(value) ? format.format(value) : 'Unavailable';

function element(tag, value, className) {
  const node = document.createElement(tag);
  if (value != null) node.textContent = value;
  if (className) node.className = className;
  return node;
}
function link(label, url, className) {
  const anchor = element('a', label, className);
  anchor.href = url;
  return anchor;
}
function options(id, rows, selected) {
  const field = get(id);
  field.replaceChildren(...rows.map(([value, label]) => new Option(label, value)));
  field.value = selected;
  field.disabled = false;
}
async function readData(name) {
  const response = await fetch(`./data/${name}.json`);
  if (!response.ok) throw new Error(`Could not load ${name}.`);
  return await response.json();
}

let icij, oecd, jurisdiction;
const countryFields = ['country', 'role', 'investigation'];
function updateQuery() {
  const url = new URL(window.location.href);
  for (const key of countryFields) {
    if (get(key).value && !(key === 'role' && get(key).value === 'entities')) {
      url.searchParams.set(key, get(key).value);
    } else {
      url.searchParams.delete(key);
    }
  }
  history.replaceState(null, '', url);
}

function matrixRow(row, country, largest) {
  const tr = element('tr');
  const heading = element('th');
  heading.scope = 'row';
  heading.append(link(row.name, `./investigations/${row.id}/`), element('br'),
    link('ICIJ records', countrySource(row, country), 'record-source'));
  const td = element('td', null, 'numeric');
  const cell = element('div', null, 'count-cell');
  const space = element('span', null, 'bar-space');
  space.setAttribute('aria-hidden', 'true');
  const bar = element('i');
  bar.style.width = largest && row.count ? `${100 * row.count / largest}%` : '0';
  space.append(bar);
  cell.append(space, element('strong', count(row.count)));
  td.append(cell);
  tr.append(heading, element('td', row.coverage || 'Unspecified by source'), td);
  return tr;
}

function renderMatrix() {
  const country = icij.countries.find(row => row.code === get('country').value);
  const role = get('role').value;
  const investigation = get('investigation').value;
  const rows = countryRows(icij, {country, role, investigation});
  const total = totalRecords(rows);
  const type = roles[role];
  const numberText = total === null ? 'Count unavailable' : `${count(total)} ${total === 1 ? type.one : type.many}`;
  const scope = investigation ? `in ${rows[0].name}` : `across ${rows.length} investigations`;
  get('matrix-title').textContent = `${country.name} · ${type.label}`;
  get('matrix-figure').textContent = `${numberText} ${scope}.`;
  get('country-profile').href = `./places/${country.code.toLowerCase()}/`;
  get('country-profile').textContent = `Open ${country.name} profile →`;
  get('count-column').textContent = type.label;
  get('role-description').textContent = `${type.help} Export dated ${icij.source_edition}.`;
  const largest = Math.max(0, ...rows.map(row => row.count || 0));
  get('matrix-rows').replaceChildren(...rows.map(row => matrixRow(row, country, largest)));
  get('matrix-links').textContent = total === 0
    ? 'Zero means no records in this category carry this country tag in the selected release or releases.'
    : 'Select an investigation for its full source breakdown, or open its country-filtered ICIJ records.';
  get('matrix').hidden = false;
  get('canada-static').hidden = true;
}

function renderReview() {
  if (!jurisdiction || !oecd) return;
  const review = matchedReview(jurisdiction, oecd.jurisdictions);
  const result = get('oecd-result');
  if (!review) {
    result.replaceChildren(element('p', `No matching jurisdiction-level assessment for ${jurisdiction.name} in this OECD table.`, 'assessment'),
      link('Open the OECD table', oecd.source.url));
    return;
  }
  const rating = review.rating || 'No overall rating published';
  const details = [];
  if (review.review_year) details.push(`Report published ${review.published_on || review.review_year}`);
  if (review.round) details.push(`Round ${review.round}`);
  result.replaceChildren(element('p', `${review.jurisdiction} · ${rating}`, 'assessment'));
  if (details.length) result.append(element('p', details.join(' · '), 'source-note'));
  if (review.status) result.append(element('p', review.status, 'source-note'));
  if (oecd.source.updated_at) result.append(element('p', `OECD table updated ${oecd.source.updated_at}.`, 'source-note'));
  result.append(link('Read the OECD assessment', review.url || oecd.source.url));
}

function renderJurisdiction() {
  jurisdiction = icij.jurisdictions.find(row => row.code === get('jurisdiction').value);
  get('incorporation-title').textContent = `${jurisdiction.name} · Entity records`;
  get('incorporation-rows').replaceChildren(...icij.investigations.map(release => {
    const row = element('div', null, 'inc-row');
    row.append(link(release.name, `./investigations/${release.id}/`), element('strong', count(jurisdiction.investigations[release.id])));
    return row;
  }));
  const sourceLabel = new URL(jurisdiction.url).searchParams.has('j') ? 'Open jurisdiction records at ICIJ' : 'Open the ICIJ database and source notes';
  get('incorporation-source').replaceChildren(link('Open the incorporation profile →', `./incorporation/${jurisdiction.code}/`), ' · ', link(sourceLabel, jurisdiction.url));
  renderReview();
}

function renderTrail(trail) {
  const byId = new Map(trail.nodes.map(node => [node.id, node]));
  const cards = element('div', null, 'relations');
  for (const edge of trail.edges) {
    const from = byId.get(edge.from);
    const to = byId.get(edge.to);
    const card = element('div', null, 'relation');
    const heading = element('h4');
    heading.append(link(from.name, from.url));
    const target = element('p', null, 'relationship-target');
    target.append(element('span', `${edge.role} of `, 'role'), link(to.name, to.url));
    card.append(heading, target, element('p', relationshipDates(edge), 'date'), link('ICIJ relationship record', edge.url));
    cards.append(card);
  }
  const credit = element('p', `${trail.dataset} · Source records through ${trail.source_cutoff}.`, 'source-note');
  const permalink = element('p', null, 'permanent');
  permalink.append(link('Open the full corporate record →', `./trails/${trail.id}/`));
  const panel = get('trail-result');
  panel.replaceChildren(element('h3', trail.title), element('p', trail.summary), credit, cards, element('p', trail.note, 'source-note'), permalink);
  if (trail.id === 'canada-trustee-bvi') {
    panel.append(link('Compare the British Virgin Islands’ incorporation counts and OECD review →', './?jurisdiction=british-virgin-islands#jurisdictions'));
  }
  if (trail.id === 'bml-betsson') {
    const related = element('p', null, 'source-links');
    related.append(
      link('Read BML Group Limited’s Malta licence profile in Gambling Regulator Watch', 'https://coolcode.ca/gamblingregulatorwatch/records/bml-group-limited-662add5114/'),
      link('Read the field note tracing BML Group Limited to dated company and licensing records', 'https://coolcode.ca/field-notes/reading-offshore-records/'),
    );
    panel.append(related);
  }
}

readData('icij').then(data => {
  icij = data;
  const selected = selectedValues(data, new URLSearchParams(location.search));
  options('country', data.countries.map(row => [row.code, row.name]), selected.country.code);
  options('investigation', [['', `All investigations (${data.investigations.length})`], ...data.investigations.map(row => [row.id, row.name])], selected.investigation);
  get('role').disabled = false;
  get('role').value = selected.role;
  for (const field of countryFields) {
    get(field).addEventListener('change', () => { renderMatrix(); updateQuery(); });
  }
  renderMatrix();
  get('source-edition').textContent = `ICIJ export dated ${data.source_edition}. Download checked ${data.checked_at}.`;
  const requestedJurisdiction = new URLSearchParams(location.search).get('jurisdiction');
  const initialJurisdiction = data.jurisdictions.find(row => row.code === requestedJurisdiction) || data.jurisdictions.find(row => row.iso3 === 'VGB') || data.jurisdictions[0];
  options('jurisdiction', data.jurisdictions.map(row => [row.code, row.name]), initialJurisdiction.code);
  get('jurisdiction').addEventListener('change', () => {
    renderJurisdiction();
    const url = new URL(location.href);
    url.searchParams.set('jurisdiction', jurisdiction.code);
    history.replaceState(null, '', url);
  });
  renderJurisdiction();
}).catch(() => {
  get('icij-status').replaceChildren('Interactive counts are unavailable. ', link('Browse the published country and investigation profiles.', './records/'));
});
readData('oecd').then(data => {
  oecd = data;
  renderReview();
}).catch(() => {
  get('oecd-status').textContent = 'The local OECD review could not load. Use the OECD ratings table in Sources and interpretation.';
});
readData('trails').then(data => {
  const initial = data.trails.find(trail => trail.id === 'canada-trustee-bvi') || data.trails[0];
  options('trail', data.trails.map(trail => [trail.id, trail.title]), initial.id);
  renderTrail(initial);
  get('trail').addEventListener('change', () => renderTrail(data.trails.find(trail => trail.id === get('trail').value)));
}).catch(() => {
  get('trail-status').replaceChildren('The interactive examples are unavailable. ', link('Read the Canadian trustee record.', './trails/canada-trustee-bvi/'));
});
