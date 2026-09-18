"""Check the role switcher: each role must render the console without blank pages."""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"
PROJECT = sys.argv[1] if len(sys.argv) > 1 else "metap2"
ROLES = ["guest", "scientist", "engineer", "auditor", "admin"]

failures = []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_context(viewport={"width": 1600, "height": 900}).new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append("PAGEERROR: %s" % e))
    page.on("console", lambda m: errors.append("CONSOLE.error: %s" % m.text) if m.type == "error" else None)

    page.goto(BASE, wait_until="domcontentloaded")
    page.evaluate("(p) => localStorage.setItem('discoveryx.activeProject', p)", PROJECT)
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(1500)

    for role in ROLES:
        errors.clear()
        # open the role selector and pick the role
        page.locator(".ant-select").first.click()
        page.wait_for_timeout(400)
        page.get_by_text("role: %s" % role, exact=True).first.click()
        page.wait_for_timeout(1200)

        # visit guardrails (the permission-sensitive page)
        page.get_by_text("合规与审计", exact=True).first.click()
        page.wait_for_timeout(2000)
        body = page.evaluate("document.body.innerText.trim().length")
        ok = body > 200
        if not ok:
            failures.append("role=%s guardrails blank" % role)
        print("  %-5s role=%-10s guardrails body=%-6d errors=%d" % ("OK" if ok else "BLANK", role, body, len(set(errors))))
        for e in dict.fromkeys(errors):
            print("        %s" % e[:180])
    browser.close()

print()
print("FAILURES:", failures or "none")
sys.exit(1 if failures else 0)
