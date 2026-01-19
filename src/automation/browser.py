from playwright.sync_api import sync_playwright

class BrowserManager:
    def __init__(self, headless=False):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.headless = headless

    def start(self):
        """Starts the browser and creates a new context/page."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        return self.page

    def stop(self):
        """Stops the browser and playwright."""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
