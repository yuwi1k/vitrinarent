import re
import http.cookiejar
import urllib.request
import urllib.parse

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    urllib.request.HTTPHandler(),
)

# Get login page
resp = opener.open("http://127.0.0.1:8000/dashboard/login")
html = resp.read().decode()
m = re.search(r'name="_csrf_token" value="([^"]+)"', html)
csrf = m.group(1) if m else "NONE"
print("CSRF:", csrf)

# Login
data = urllib.parse.urlencode({"username": "admin", "password": "admin123", "_csrf_token": csrf}).encode()

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

no_redir = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    NoRedirectHandler(),
)

try:
    login_resp = no_redir.open(urllib.request.Request("http://127.0.0.1:8000/dashboard/login", data=data, method="POST"))
    print("Login:", login_resp.status)
except urllib.error.HTTPError as e:
    print("Login:", e.code, "Location:", e.headers.get("Location", "none"))
    if e.code != 303:
        print("LOGIN FAILED")
        exit(1)

pages = [
    "/dashboard/",
    "/dashboard/properties",
    "/dashboard/properties/new",
    "/dashboard/statistics",
    "/dashboard/messages",
    "/dashboard/scheduler",
    "/dashboard/feed-errors",
    "/dashboard/settings",
    "/dashboard/settings/password",
    "/dashboard/settings/notifications",
    "/dashboard/folders",
    "/dashboard/promotion",
]

all_ok = True
for url in pages:
    try:
        r = opener.open("http://127.0.0.1:8000" + url)
        text = r.read().decode()
        code = r.status
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        code = e.code

    has_error = any(kw in text for kw in ["Traceback", "Internal Server Error", "TemplateSyntaxError", "UndefinedError"])
    title_match = re.search(r"<title>(.+?)</title>", text)
    title = title_match.group(1).strip() if title_match else "NO TITLE"
    status = "ERROR" if has_error else "OK"
    if has_error or code >= 500:
        all_ok = False
        status = "ERROR"
    print(f"  {url:45s} -> {code} | {status:5s} | {len(text):6d} bytes | {title}")

print()
if all_ok:
    print("ALL PAGES OK")
else:
    print("SOME PAGES HAVE ERRORS")
