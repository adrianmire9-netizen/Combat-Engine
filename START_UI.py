"""Double-click or run with Python to start the UI and open your browser."""
import threading
import webbrowser
from combat_engine.web import main

if __name__ == '__main__':
    threading.Timer(1, lambda: webbrowser.open('http://127.0.0.1:8765')).start()
    main()
