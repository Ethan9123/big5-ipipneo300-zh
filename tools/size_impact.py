# -*- coding: utf-8 -*-
"""What does shipping the empirical tables actually cost over the wire?"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(os.path.dirname(HERE), "site", "index.html")
PAYLOAD = os.path.join(HERE, "out", "pct_tables_encoded.txt")

try:
    import brotli
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "brotli"], check=False)
    import brotli

html = io.open(SITE, encoding="utf-8").read()
payload = io.open(PAYLOAD, encoding="utf-8").read().strip()
decoder = io.open(os.path.join(HERE, "out", "decoder.js"), encoding="utf-8").read()

# strip the block comment + module.exports tail that will not ship
ship_decoder = decoder.split("*/", 1)[1].split("if (typeof module")[0].strip()

def bro(s):
    return len(brotli.compress(s.encode("utf-8"), quality=11))

base_raw = len(html.encode("utf-8"))
base_bro = bro(html)

# what the page looks like with the tables + decoder added, and the old
# cubic/clamp machinery removed (CUB, cubic, clampPct ~ 300 bytes, negligible)
added = '\nconst PCTT = decodePctTables("%s");\n' % payload
new_html = html.replace("</script>", ship_decoder + added + "</script>", 1)
new_raw = len(new_html.encode("utf-8"))
new_bro = bro(new_html)

print("payload (encoded tables)")
print("   raw    : %7d bytes" % len(payload.encode("utf-8")))
print("   brotli : %7d bytes  (alone)" % bro(payload))
print("decoder JS (comment stripped)")
print("   raw    : %7d bytes" % len(ship_decoder.encode("utf-8")))
print()
print("page today")
print("   raw    : %7d bytes" % base_raw)
print("   brotli : %7d bytes" % base_bro)
print("page with empirical tables")
print("   raw    : %7d bytes   (+%d, +%.1f%%)" % (new_raw, new_raw - base_raw, 100.0 * (new_raw - base_raw) / base_raw))
print("   brotli : %7d bytes   (+%d, +%.1f%%)" % (new_bro, new_bro - base_bro, 100.0 * (new_bro - base_bro) / base_bro))
print()
print("for reference, the live server sent 73677 brotli bytes for the current page.")
