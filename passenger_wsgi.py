import sys
import os

# Limit OpenBLAS and OMP threads to avoid resource temporarily unavailable errors on shared hosting
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['LSAPI_CHILDREN'] = '24'

# Insert the current directory (project root) into Python path
sys.path.insert(0, os.path.dirname(__file__))

# Insert the 'app' directory into the path as well
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Passenger looks for a variable named 'application'
from app.main import app as application
