"""Explicit manual login or offline Chromium smoke check; never a crawl job."""
import argparse
import json
import time

from src.browser.profiles import PLATFORMS, ProfileInUse, locked_profile, prepare_browser_path

URLS = {"facebook": "https://www.facebook.com/", "tiktok": "https://www.tiktok.com/", "threads": "https://www.threads.com/"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare a dedicated Facebook/TikTok/Threads browser profile.")
    parser.add_argument("--platform", required=True, choices=PLATFORMS)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--login", action="store_true", help="Open Chromium for manual sign-in; no automated login.")
    mode.add_argument("--smoke", action="store_true", help="Headless local-page check, with no platform request.")
    parser.add_argument("--timeout", type=int, default=1200, help="Maximum manual login seconds (1-1200).")
    parser.add_argument("--channel", choices=('chromium','chrome'), help="Use installed Chrome with the same dedicated project profile.")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 1200:
        parser.error("timeout must be between 1 and 1200 seconds")
    prepare_browser_path()
    try:
        from playwright.sync_api import Error, sync_playwright
        with locked_profile(args.platform) as profile, sync_playwright() as playwright:
            print(f"Browser profile: {profile.resolve()}", flush=True)
            channel=args.channel or ('chrome' if args.platform=='threads' else 'chromium')
            context = playwright.chromium.launch_persistent_context(str(profile.resolve()), headless=args.smoke,
                **({'channel':'chrome'} if channel=='chrome' else {}))
            closed = [False]
            context.on("close", lambda _: closed.__setitem__(0, True))
            try:
                page = context.pages[0] if context.pages else context.new_page()
                if args.smoke:
                    page.set_content("<html><title>Local browser smoke</title><body>ready</body></html>")
                    if page.title() != "Local browser smoke":
                        raise RuntimeError("Chromium smoke check failed")
                    print(json.dumps({"platform": args.platform, "chromium": context.browser.version,
                                      "outcome": "LOCAL_SMOKE_PASSED", "platform_access_verified": False}))
                else:
                    page.goto(URLS[args.platform], wait_until="domcontentloaded", timeout=30000)
                    print("Sign in manually in Chromium, then close the browser window and wait for this command to finish before reopening.")
                    print("Each launch opens the platform home page; this alone does not mean you were signed out. No credential is read or logged.")
                    deadline = time.monotonic() + args.timeout
                    while not closed[0] and context.pages and time.monotonic() < deadline:
                        page = context.pages[-1]
                        try:
                            page.wait_for_timeout(500)
                        except Error:
                            if closed[0] or page.is_closed():
                                break
                            raise
                    print("Login window finished. Verify public-source access separately before enabling a source.")
            finally:
                if not closed[0]:
                    context.close()
    except ImportError:
        parser.exit(2, "Install requirements-browser.txt and Playwright Chromium first.\n")
    except ProfileInUse as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
