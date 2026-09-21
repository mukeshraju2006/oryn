from oryn.applications.browsers.adapter import BrowserAdapter


adapter = BrowserAdapter()

adapter.start_browser()

print("Chrome started.")

print("\nOpen URLs:")

for url in adapter.capture_urls():
    print(url)

