from oryn.applications.browsers.adapter import BrowserAdapter


adapter = BrowserAdapter()

print("Chrome must already be open.")

print("\nOpen URLs:")

urls = adapter.capture_urls()

for url in urls:
    print(url)

print(f"\nTotal: {len(urls)}")