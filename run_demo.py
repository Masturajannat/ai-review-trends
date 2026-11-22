"""Start the dummy shop and Review Coach together and open the shop in the browser.

    python run_demo.py

Shop: http://localhost:8502   Review Coach: http://localhost:8501 (opened from a product page).
Press Ctrl+C here to stop both.
"""
import os, subprocess, sys, time, webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
SHOP, COACH = os.path.join(ROOT, "shop"), os.path.join(ROOT, "review_coach")

if not os.path.exists(os.path.join(SHOP, "shop.db")):                      # first run: make the shop database
    subprocess.run([sys.executable, "build_shop_db.py"], cwd=SHOP, check=True)


def streamlit(folder, script, port):
    return subprocess.Popen([sys.executable, "-m", "streamlit", "run", script, "--server.port", str(port),
                             "--server.headless", "true"], cwd=folder)


procs = [streamlit(COACH, "app.py", 8501), streamlit(SHOP, "shop_app.py", 8502)]
time.sleep(4)
webbrowser.open("http://localhost:8502")
try:
    for p in procs:
        p.wait()
except KeyboardInterrupt:
    pass
finally:
    for p in procs:
        p.terminate()
