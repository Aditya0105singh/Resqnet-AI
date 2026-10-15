import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RESQNET_DB", os.path.join(os.path.dirname(__file__), "test.db"))
