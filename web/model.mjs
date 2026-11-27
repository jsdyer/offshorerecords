export const roles = {
  entities: {label: 'Entities', one: 'entity record', many: 'entity records', help: 'Entities include companies, trusts and other legal arrangements.'},
  officers: {label: 'Officers', one: 'officer record', many: 'officer records', help: 'Officers are people or organisations with a recorded role, such as a shareholder or director.'},
  intermediaries: {label: 'Intermediaries', one: 'intermediary record', many: 'intermediary records', help: 'Intermediaries are service providers that helped arrange or administer offshore entities.'},
  addresses: {label: 'Addresses', one: 'address record', many: 'address records', help: 'Addresses count location records with the selected country link.'},
  others: {label: 'Other records', one: 'other record', many: 'other records', help: 'Other records are nodes the source classifies outside the entity, officer, intermediary and address groups.'},
};

export function selectedValues(data, params) {
  const country = data.countries.find(row => row.code === params.get('country')?.toUpperCase())
    || data.countries.find(row => row.code === 'CAN') || data.countries[0];
  const investigation = data.investigations.find(row => row.id === params.get('investigation'));
  const requestedRole = params.get('role');
  const role = Object.hasOwn(roles, requestedRole) ? requestedRole : 'entities';
  return {country, role, investigation: investigation?.id || ''};
}

export function countryRows(data, {country, role, investigation}) {
  return data.investigations.filter(row => !investigation || row.id === investigation).map(row => ({
    ...row,
    count: country.investigations[row.id]?.[role] ?? null,
  }));
}

export function totalRecords(rows) {
  return rows.length && rows.every(row => Number.isInteger(row.count))
    ? rows.reduce((total, row) => total + row.count, 0) : null;
}

export function matchedReview(jurisdiction, reviews) {
  if (!jurisdiction || !/^[A-Z]{3}$/.test(jurisdiction.iso3 || '')) return null;
  return reviews.find(review => review.iso3 === jurisdiction.iso3) || null;
}

export function countrySource(release, country) {
  const url = new URL(release.url);
  url.searchParams.set('c', country.code);
  return url.href;
}

export function relationshipDates(edge) {
  if (edge.start_date && edge.end_date) return `From ${edge.start_date} to ${edge.end_date}.`;
  if (edge.start_date) return `Recorded start ${edge.start_date}. End date unavailable.`;
  if (edge.end_date) return `Recorded end ${edge.end_date}. Start date unavailable.`;
  return 'Relationship dates unavailable.';
}
