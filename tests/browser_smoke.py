"""Open the published project subpath and follow real saved records in Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BML_LICENCE = "https://coolcode.ca/gamblingregulatorwatch/records/bml-group-limited-662add5114/"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def data(name):
    return json.loads((DIST / "data" / f"{name}.json").read_text())


def check_desktop(page, url):
    archive = data("icij")
    investigations = archive["investigations"]
    canada = next(p for p in archive["countries"] if p["code"] == "CAN")
    trails = data("trails")["trails"]
    page.goto(url)
    expect(page.get_by_label("Find a country")).to_have_value("CAN")
    expect(page.locator("#matrix-rows tr")).to_have_count(len(investigations))
    expected = [f"{canada['investigations'][inv['id']]['entities']:,}" for inv in investigations]
    assert page.locator("#matrix-rows strong").all_text_contents() == expected
    assert page.locator("#matrix-rows .record-source").first.get_attribute("href").endswith("?c=CAN")
    expect(page.locator("#canada-static")).to_be_hidden()
    assert page.locator("#country-profile").get_attribute("href") == "./places/can/"
    page.get_by_label("Find a country").select_option("MLT")
    page.get_by_label("Record type", exact=True).select_option("officers")
    page.get_by_label("Investigation", exact=True).select_option("panama-papers")
    expect(page.locator("#matrix-rows tr")).to_have_count(1)
    malta = next(p for p in archive["countries"] if p["code"] == "MLT")
    expect(page.locator("#matrix-rows strong")).to_have_text(f"{malta['investigations']['panama-papers']['officers']:,}")
    assert "country=MLT" in page.url and "role=officers" in page.url and "investigation=panama-papers" in page.url
    page.reload()
    expect(page.locator("#matrix-title")).to_have_text("Malta · Officers")
    page.locator("#country-profile").click()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Malta")
    page.goto(url + "?jurisdiction=malta#jurisdictions")
    expect(page.locator("#jurisdiction")).to_have_value("malta")
    review = next(r for r in data("oecd")["jurisdictions"] if r["iso3"] == "MLT")
    expect(page.locator("#oecd-result")).to_contain_text(review["rating"])
    expect(page.locator("#oecd-result")).to_contain_text(f"Report published {review['review_year']}")
    expect(page.locator("#oecd-result a")).to_have_attribute("href", review["url"])
    page.locator("#incorporation-source a").first.click()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Malta")
    page.go_back()
    page.get_by_label("Incorporation jurisdiction").select_option("alaska")
    expect(page.locator("#oecd-result")).to_contain_text("No matching jurisdiction-level assessment")
    assert "jurisdiction=alaska" in page.url
    for trail in trails:
        page.get_by_label("Corporate example").select_option(trail["id"])
        panel = page.locator("#trail-result")
        expect(panel).to_contain_text(trail["title"])
        expect(panel.locator(".relation")).to_have_count(len(trail["edges"]))
        node = next(n for n in trail["nodes"] if n["id"] == trail["edges"][0]["from"])
        expect(panel.locator(".relation h4 a").first).to_have_attribute("href", node["url"])
        expect(panel.locator(".permanent a")).to_have_attribute("href", f"./trails/{trail['id']}/")
        licence_link = panel.locator(f'a[href="{BML_LICENCE}"]')
        expect(licence_link).to_have_count(1 if trail["id"] == "bml-betsson" else 0)
    page.locator("#trail-result .permanent a").click()
    expect(page.get_by_role("heading", level=1)).to_have_text(trails[-1]["title"])
    page.goto(url + "?country=CAN&role=entities&investigation=bahamas-leaks")
    expect(page.locator("#matrix-rows strong")).to_have_text(str(canada["investigations"]["bahamas-leaks"]["entities"]))
    if canada["investigations"]["bahamas-leaks"]["entities"] == 0:
        expect(page.locator("#matrix-links")).to_contain_text("Zero means")


def check_phone(page, url, screenshots):
    page.goto(url)
    expect(page.locator("#matrix")).to_be_visible()
    for selector in ["#country", ".opening-case", "#matrix-figure", "#matrix-rows tr:first-child strong"]:
        box = page.locator(selector).bounding_box()
        assert box and box["y"] + box["height"] < 844, selector
    assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
    expect(page.locator("#role-description")).to_contain_text(data("icij")["source_edition"])
    page.screenshot(path=str(screenshots / "mobile.png"))
    page.get_by_label("Record type", exact=True).select_option("intermediaries")
    expect(page.locator("#matrix-title")).to_have_text("Canada · Intermediaries")
    page.get_by_label("Corporate example").select_option("canada-trustee-bvi")
    expect(page.locator("#trail-result")).to_contain_text("ONEIPA LIMITED")
    expect(page.locator("#trail-result")).to_contain_text("Relationship dates unavailable")
    assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")


def check_static(page, url):
    page.goto(url)
    expect(page.locator("#canada-static table")).to_be_visible()
    expect(page.locator("#canada-static tbody tr")).to_have_count(len(data("icij")["investigations"]))
    expect(page.locator("#canada-static caption")).to_contain_text("Canada")
    assert all("?c=CAN" in href for href in page.locator("#canada-static a").evaluate_all("(a) => a.map(x => x.href)"))
    assert page.evaluate("document.documentElement.scrollWidth === window.innerWidth")
    page.locator(".opening-case").click()
    expect(page.get_by_role("heading", level=1)).to_contain_text("Canadian trustee")
    expect(page.locator(f'a[href="{BML_LICENCE}"]')).to_have_count(0)
    page.goto(url + "trails/bml-betsson/")
    licence_link = page.get_by_role("link", name="Read BML Group Limited’s Malta licence profile in Gambling Regulator Watch")
    expect(licence_link).to_have_attribute("href", BML_LICENCE)
    expect(licence_link.locator("..").get_by_role("link", name="Read the field note", exact=False)).to_be_visible()


def main():
    screenshots = ROOT / "browser-checks"
    screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "offshorerecords").symlink_to(DIST, target_is_directory=True)
        # The shared hub supplies this relative-root asset in production.
        (Path(tmp) / "assets").mkdir()
        (Path(tmp) / "assets" / "tool-metrics.js").write_text("")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=tmp))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/offshorerecords/"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH"))
                errors = []
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.on("pageerror", lambda err: errors.append(str(err)))
                check_desktop(page, url)
                page.goto(url)
                expect(page.locator("#matrix")).to_be_visible()
                page.screenshot(path=str(screenshots / "desktop.png"))
                phone = browser.new_page(viewport={"width": 390, "height": 844})
                phone.on("pageerror", lambda err: errors.append(str(err)))
                check_phone(phone, url, screenshots)
                static = browser.new_page(java_script_enabled=False, viewport={"width": 390, "height": 844})
                check_static(static, url)
                fallback = browser.new_page()
                fallback.route("**/data/icij.json", lambda route: route.abort())
                fallback.goto(url)
                expect(fallback.locator("#icij-status")).to_contain_text("Interactive counts are unavailable")
                expect(fallback.locator("#canada-static table")).to_be_visible()
                expect(fallback.locator("#trail-result h3")).to_contain_text("Canadian trustee")
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    print("Atlas browser checks passed: archive filters and stable links, OECD matches, corporate examples, mobile, script-free Canada and source failure.")


if __name__ == "__main__":
    main()
