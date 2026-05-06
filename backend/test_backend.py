import json
import urllib.request
import time

url = "http://127.0.0.1:5000/analyze"
body = {"message": "def foo():\n    return 'hello world'\n"}

data = json.dumps(body).encode("utf-8")
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

try:
    resp = urllib.request.urlopen(req, timeout=8)
    print(resp.read().decode())
except Exception as e:
    print("ERROR:", e)
