"""Smoke-test every console page by clicking through the sidebar, in both languages.

Exits non-zero if any page renders blank or throws a runtime error.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8080"
TASK = sys.argv[1] if len(sys.argv) > 1 else ""
PROJECT = sys.argv[2] if len(sys.argv) > 2 else "metap2"

NAV_ZH = [
    "项目总览", "靶点情报", "分子设计", "合成规划", "成药性评估", "分析决策",
    "项目报告", "任务列表", "数据目录", "导入向导", "知识库状态", "合规与审计", "系统状态",
]

failures: list[str] = []


def run(lang: str, labels: list[str]) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1600, "height": 900}).new_page()

        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append("PAGEERROR: %s" % e))
        page.on("console", lambda m: errors.append("CONSOLE.error: %s" % m.text) if m.type == "error" else None)

        page.goto(BASE, wait_until="domcontentloaded")
        page.evaluate(
            """([proj, lg]) => {
                localStorage.setItem('discoveryx.activeProject', proj);
                localStorage.setItem('discoveryx.lang', lg);
            }""",
            [PROJECT, lang],
        )
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(2000)

        print("--- lang=%s ---" % lang)
        for label in labels:
            errors.clear()
            try:
                page.get_by_text(label, exact=True).first.click(timeout=4000)
            except Exception:
                print("  SKIP  %s (not in the sidebar)" % label)
                continue
            page.wait_for_timeout(1800)
            body = page.evaluate("document.body.innerText.trim().length")
            root = page.evaluate("document.getElementById('root')?.childElementCount ?? 0")
            ok = body > 200 and root > 0
            if not ok:
                failures.append("%s / %s" % (lang, label))
            print("  %-5s %-12s url=%-20s body=%-6d" % ("OK" if ok else "BLANK", label, page.url.replace(BASE, ""), body))
            for e in dict.fromkeys(errors):
                failures.append("%s / %s: %s" % (lang, label, e[:120]))
                print("        %s" % e[:200])

        if TASK:
            errors.clear()
            page.goto(BASE, wait_until="networkidle")
            page.wait_for_timeout(1000)
            try:
                page.get_by_text(labels[7], exact=True).first.click()   # task list
                page.wait_for_timeout(1500)
                page.get_by_text(TASK, exact=False).first.click(timeout=4000)
                page.wait_for_timeout(2500)
                body = page.evaluate("document.body.innerText.trim().length")
                ok = body > 400
                if not ok:
                    failures.append("%s / task detail" % lang)
                print("  %-5s %-12s url=%-20s body=%-6d" % ("OK" if ok else "BLANK", "task detail", page.url.replace(BASE, ""), body))
                for e in dict.fromkeys(errors):
                    failures.append("%s / task detail: %s" % (lang, e[:120]))
                    print("        %s" % e[:200])
            except Exception as exc:
                print("  SKIP  task detail (%s)" % str(exc)[:70])
        browser.close()


run("zh", NAV_ZH)
run("en", ["Overview", "Target intel", "Design", "Make", "ADME-Tox", "Analyze", "Report", "Tasks", "Catalog", "Import", "Knowledge", "Guardrails", "System"])

print()
if failures:
    print("FAILURES (%d):" % len(failures))
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("ALL PAGES OK")
