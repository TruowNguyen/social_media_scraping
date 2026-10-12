"""One persistent context per platform job, bounded navigation, no traces."""
from contextlib import contextmanager
from urllib.parse import urlsplit
from src.browser.profiles import ProfileInUse, locked_profile, prepare_browser_path
from src.acquisition.models import AdapterError
from src.config.env import env_str


@contextmanager
def browser_job(platform, deadline, headless=True):
    from playwright.sync_api import sync_playwright
    prepare_browser_path()
    try:
        with locked_profile(platform) as path, sync_playwright() as playwright:
            channel=env_str('THREADS_BROWSER_CHANNEL','chrome') if platform=='threads' else 'chromium'
            if channel not in {'chrome','chromium'}:raise ValueError('Unsupported browser channel')
            context = playwright.chromium.launch_persistent_context(str(path), headless=headless, timeout=deadline.milliseconds(), accept_downloads=False,
                **({'channel':'chrome'} if channel=='chrome' else {}))
            try:
                context.set_default_timeout(deadline.milliseconds(5000))
                # Render pages but prevent video/audio acquisition and playback.
                context.route("**/*", lambda route: route.abort() if route.request.resource_type == "media" else route.continue_())
                page = context.pages[0] if context.pages else context.new_page()
                yield page
            finally:
                context.close()
    except ProfileInUse:
        raise AdapterError("SKIPPED", "PROFILE_IN_USE") from None


def page_failure(page):
    """Inspect only access UI; never put page text in an error/log."""
    pathname = urlsplit(page.url).path
    if any(token in pathname for token in ("/login", "/checkpoint")):
        return ("AUTH_REQUIRED", "LOGIN_REQUIRED")
    checks = [
        ('iframe[src*="captcha"], [id*="captcha"], [data-e2e="captcha"]', "ACCESS_DENIED", "CAPTCHA"),
        ('input[name="email"], input[name="pass"]', "AUTH_REQUIRED", "LOGIN_REQUIRED"),
    ]
    for selector, status, code in checks:
        locator = page.locator(selector)
        if locator.count() and any(locator.nth(i).is_visible() for i in range(locator.count())):
            return status, code
    # Facebook's unavailable-content screen uses ordinary spans, not headings.
    # Exact visible text on a page without articles avoids matching complaint text.
    if not page.locator('[role="article"]').count():
        for phrase in ("Bạn hiện không xem được nội dung này", "This content isn't available right now",
                       "This content isn't available at the moment"):
            notice = page.get_by_text(phrase, exact=True)
            if any(notice.nth(i).is_visible() for i in range(notice.count())):
                return ("SOURCE_UNAVAILABLE", "CONTENT_UNAVAILABLE")
    # Restrict phrases to headings/status UI so a post mentioning an error is not a block.
    text = " ".join(page.locator('h1, h2, [role="alert"], [data-e2e="error-page"]').all_text_contents()).casefold()
    for phrases, status, code in [
        (("private group", "nhóm riêng tư"), "ACCESS_DENIED", "PRIVATE_GROUP"),
        (("too many requests", "quá nhiều yêu cầu"), "RATE_LIMITED", "RATE_LIMIT"),
        (("content isn't available", "page not available", "nội dung này hiện không", "không tìm thấy"), "SOURCE_UNAVAILABLE", "SOURCE_NOT_FOUND"),
    ]:
        if any(phrase in text for phrase in phrases):
            return status, code
    return None


def navigate(page, url, deadline):
    from playwright.sync_api import TimeoutError, Error
    for attempt in range(2):
        deadline.check()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=deadline.milliseconds())
            if response and response.status == 429:
                raise AdapterError("RATE_LIMITED", "HTTP_429")
            if response and response.status in {401, 403}:
                raise AdapterError("ACCESS_DENIED", "HTTP_ACCESS_DENIED")
            if response and response.status == 404:
                raise AdapterError("SOURCE_UNAVAILABLE", "HTTP_404")
            if response and response.status >= 500:
                if attempt == 0 and deadline.remaining() > 1:
                    continue
                raise AdapterError("SOURCE_UNAVAILABLE", "HTTP_SERVER_ERROR")
            failure = page_failure(page)
            if failure:
                raise AdapterError(*failure)
            return
        except TimeoutError:
            if attempt == 1 or deadline.remaining() < 1:
                raise AdapterError("BUDGET_EXHAUSTED", "NAVIGATION_TIMEOUT") from None
        except Error:
            if attempt == 1 or deadline.remaining() < 1:
                raise AdapterError("SOURCE_UNAVAILABLE", "BROWSER_NAVIGATION_FAILED") from None
