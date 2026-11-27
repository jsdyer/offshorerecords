import {test} from 'node:test';
import assert from 'node:assert/strict';
import {countryRows, countrySource, matchedReview, relationshipDates, selectedValues, totalRecords} from '../web/model.mjs';

const data = {
  investigations: [
    {id: 'first', name: 'First release', url: 'https://offshoreleaks.icij.org/investigations/first'},
    {id: 'second', name: 'Second release'},
  ],
  countries: [
    {code: 'AUS', name: 'Australia', investigations: {first: {entities: 12, officers: 0}, second: {officers: 4}}},
    {code: 'CAN', name: 'Canada', investigations: {first: {entities: 0, officers: 12}, second: {entities: 8, officers: 17}}},
  ],
};

test('Canada opens with all releases, and bad presets recover to the Canadian overview', () => {
  for (const query of ['', 'country=nope&role=toString&investigation=unknown']) {
    const selected = selectedValues(data, new URLSearchParams(query));
    assert.equal(selected.country.code, 'CAN');
    assert.equal(selected.investigation, '');
    assert.equal(selected.role, 'entities');
    assert.equal(totalRecords(countryRows(data, selected)), 8);
  }
});

test('older links and lowercase country codes resolve independent role and investigation selectors', () => {
  const selected = selectedValues(data, new URLSearchParams('country=aus&role=officers&investigation=first'));
  assert.equal(selected.country.code, 'AUS');
  assert.deepEqual(countryRows(data, selected).map(row => [row.id, row.count]), [['first', 0]]);
  assert.equal(countrySource(data.investigations[0], selected.country), 'https://offshoreleaks.icij.org/investigations/first?c=AUS');
});

test('missing counts never display as zero or silently contribute to a total', () => {
  const selected = selectedValues(data, new URLSearchParams('country=AUS'));
  const rows = countryRows(data, selected);
  assert.deepEqual(rows.map(row => row.count), [12, null]);
  assert.equal(totalRecords(rows), null);
  assert.equal(totalRecords([]), null);
});

test('OECD context requires an explicit ISO jurisdiction mapping', () => {
  const reviews = [{iso3: 'USA', rating: 'US'}, {iso3: 'VGB', rating: null}, {iso3: null, rating: 'orphan'}];
  assert.equal(matchedReview({code: 'BVI', iso3: 'VGB'}, reviews), reviews[1]);
  assert.equal(matchedReview({code: 'USA', name: 'Alaska', iso3: null}, reviews), null);
  assert.equal(matchedReview({code: 'alaska', name: 'Alaska', iso3: ''}, reviews), null);
});

test('a missing relationship endpoint date is explained independently of a source cutoff', () => {
  assert.equal(relationshipDates({start_date: null, end_date: null}), 'Relationship dates unavailable.');
  assert.match(relationshipDates({start_date: '2010-03-12'}), /2010-03-12.*End date unavailable/);
  assert.match(relationshipDates({end_date: '2015-06-12'}), /2015-06-12.*Start date unavailable/);
  assert.equal(relationshipDates({start_date: '2000-01-01', end_date: '2004-01-01'}), 'From 2000-01-01 to 2004-01-01.');
});
