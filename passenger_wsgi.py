"""
passenger_wsgi.py
HostPinnacle cPanel Phusion Passenger WSGI entry point for FindYourMatch (MMUST Dating AI).
cPanel CloudLinux Python Selector looks for this file and expects a callable named `application`.
"""
import sys
import os

# 1. Limit OpenBLAS and OMP threads to avoid resource exhaustion on shared hosting
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['LSAPI_CHILDREN'] = '24'

# 2. Determine project root and add to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

app_dir = os.path.join(PROJECT_ROOT, 'app')
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# 3. Anchor current working directory to project root
# This guarantees relative paths (firebase_key.json, .env, templates, static) resolve properly
os.chdir(PROJECT_ROOT)

# 4. Explicitly load environment variables from .env
try:
    from dotenv import load_dotenv
    dotenv_file = os.path.join(PROJECT_ROOT, '.env')
    if os.path.exists(dotenv_file):
        load_dotenv(dotenv_file)
except ImportError:
    pass

# 5. Production defaults for cPanel
os.environ.setdefault('FLASK_ENV', 'production')

# 6. Import and expose the WSGI application callable with diagnostic fallback
try:
    from app.main import app as application
except Exception as e:
    import traceback
    error_traceback = traceback.format_exc()
    print("FATAL: Failed to start FindYourMatch Flask application via passenger_wsgi.py:\n" + error_traceback, file=sys.stderr)

    # Diagnostic WSGI fallback to display the exact startup error if any dependency is missing
    def application(environ, start_response):
        status = '500 Internal Server Error'
        body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HostPinnacle cPanel - Application Startup Error</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; }}
    .card {{ max-width: 850px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.4); border-top: 4px solid #ef4444; }}
    h1 {{ color: #ef4444; font-size: 22px; margin-top: 0; }}
    p {{ color: #94a3b8; font-size: 14px; line-height: 1.6; }}
    pre {{ background: #090d16; color: #fca5a5; padding: 20px; border-radius: 8px; overflow-x: auto; font-size: 13px; line-height: 1.5; border: 1px solid #334155; }}
    .badge {{ display: inline-block; background: #374151; color: #93c5fd; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; margin-bottom: 16px; }}
    .tips {{ background: #0d2847; border-left: 4px solid #3b82f6; padding: 16px; border-radius: 6px; margin-top: 20px; }}
    .tips h3 {{ margin: 0 0 8px 0; font-size: 14px; color: #60a5fa; }}
    .tips ul {{ margin: 0; padding-left: 20px; color: #cbd5e1; font-size: 13px; }}
    .tips li {{ margin-bottom: 6px; }}
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">HostPinnacle cPanel Diagnostic</span>
    <h1>FindYourMatch Startup Exception</h1>
    <p>The application could not be loaded by Phusion Passenger. Below is the exact exception traceback:</p>
    <pre>{error_traceback}</pre>
    <div class="tips">
      <h3>Quick Fix Checklist:</h3>
      <ul>
        <li>In cPanel &rarr; <strong>Setup Python App</strong>, ensure all packages in <code>requirements.txt</code> are installed via <strong>"Run Pip Install"</strong>.</li>
        <li>Make sure <code>.env</code> and <code>firebase_key.json</code> exist in the application root directory.</li>
        <li>After resolving, click <strong>"Restart"</strong> in the cPanel Python App manager.</li>
      </ul>
    </div>
  </div>
</body>
</html>""".encode('utf-8')
        response_headers = [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Content-Length', str(len(body)))
        ]
        start_response(status, response_headers)
        return [body]

