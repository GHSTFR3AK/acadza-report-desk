#!/usr/bin/env python3
"""Bundle the console into one self-contained HTML file (dist/report-desk.html) for quick sharing or preview."""
import os
R = os.path.dirname(os.path.abspath(__file__))
rd = lambda p: open(os.path.join(R, "console", p), encoding="utf-8").read()
html = rd("index.html")
html = html.replace('<link rel="stylesheet" href="styles.css">', "<style>\n" + rd("styles.css") + "\n</style>")
html = html.replace('<script src="data.js"></script>', "<script>\n" + rd("data.js").replace("</script", "<\\/script") + "\n</script>")
html = html.replace('<script src="app.js"></script>', "<script>\n" + rd("app.js") + "\n</script>")
os.makedirs(os.path.join(R, "dist"), exist_ok=True)
open(os.path.join(R, "dist", "report-desk.html"), "w", encoding="utf-8").write(html)
print("wrote dist/report-desk.html", len(html) // 1024, "KB")
