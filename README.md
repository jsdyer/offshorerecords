# Offshore Records Atlas

Explore five investigations in the International Consortium of Investigative Journalists’ Offshore Leaks Database. Open the atlas on Canada, switch the linked country, or follow a documented organization’s role to an offshore company. Every published place and investigation has its own source-linked summary.

<!-- coolcode:guide -->
Start with Canada in the Pandora Papers. Compare the number of directly tagged entities, officers and addresses. Follow a recorded company relationship to its ICIJ source, then check the jurisdiction of incorporation and the years covered. The OECD panel dates its separate review of how the jurisdiction exchanges tax information on request.
<!-- /coolcode:guide -->

The source counts describe entries in historical records. An officer can be a person or a company. One record can refer to multiple countries. Its country tag can come from residence, a correspondence address, nationality or other source-specific fields. The incorporation jurisdiction is a separate field. Case findings, amounts of money or current ownership require additional evidence.

## Data and reuse

ICIJ publishes structured data for the Offshore Leaks, Panama Papers, Bahamas Leaks, Paradise Papers and Pandora Papers investigations. The five investigations have different providers, coverage periods and fields. The original database is made available by the **International Consortium of Investigative Journalists** under [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). ICIJ contents are available under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). The extracted ICIJ data and cited ICIJ contents distributed here carry those respective licences. CoolCode aggregates public records and supplies the presentation. [Original archives and credits](https://offshoreleaks.icij.org/pages/database).

The [OECD Global Forum](https://www.oecd.org/en/networks/global-forum-tax-transparency/resources/exchange-of-information-on-request-ratings.html) independently reviews jurisdictions’ implementation of the exchange of information on request standard. A jurisdiction rating and its publication date describe that review. They cannot establish anything about the conduct of a business appearing in the archive.

## Build and refresh

The offline site build reads saved editions from `data/`. Run `python scripts/build.py`, then `python -m http.server 8000 --directory dist`. Open [the local atlas](http://localhost:8000/). The Python and JavaScript tests run with `python -m unittest discover -s tests -v` and `node --test tests/*.test.mjs`. Install `tests/browser-requirements.txt` and Chromium to run `python tests/browser_smoke.py`.

The GitHub Actions schedule checks the sources at 11:23 UTC on the third day of each month. A manual workflow dispatch also checks the sources. A code push rebuilds the saved data. A successful refresh validates the inputs, builds the result pages, tests the site, preserves the checked data and deploys to Pages. A failed collection leaves the last published edition available with its actual check dates. A new check does not extend a historical investigation’s coverage.

Searches run inside the browser. Links to original records open the publisher’s site. The CoolCode deployment includes the shared aggregate visitor counter.

## Expand or customize

The ICIJ importer reads every typed node table in the official CSV archive. `config/icij.json` defines the five investigations, linked-country display names, reviewed incorporation labels and explicit geographic matches. Edit this file when a publisher adds a source or a jurisdiction name changes. Unassigned tags and incorporation fields are retained in their own counts. A shared name or abbreviation alone is insufficient to attach an OECD assessment. Historical, territorial and ambiguous labels can have no OECD match.

The worked relationship examples are curated in `collectors/trails.py`. Set the ICIJ node IDs, organization names and the exact role you want to demonstrate. Verify every edge and keep missing dates unknown. The check reads the original node pages and, during a combined refresh, the corresponding relationship in the public ZIP. Individual home addresses and natural-person profiles are outside the atlas. The downloadable country counts contain no individual names or street addresses.

Run `python scripts/refresh.py` with Python 3.11 or newer to download the current ICIJ ZIP, aggregate it, verify the example relationships and refresh the OECD table. The OECD collector attaches a dated publication URL where an unambiguous publisher record is available. `python scripts/build.py` and `python scripts/check_pages.py` rebuild and verify every canonical page and internal route before publishing. An ICIJ export date identifies when the file was generated. The investigation cutoff dates identify what time period the underlying historical records cover.

The linked-country view belongs to the node’s country tags. The incorporation view belongs to the entity’s registered jurisdiction. The two views keep their populations separate. A source label can represent a provider or a corporate registry; any ranking of counts here describes only the contents of this archive.
