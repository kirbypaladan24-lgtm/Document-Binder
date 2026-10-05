"""Entry point — run with:  python main.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ui.main_window import run

if __name__ == "__main__":
    run()
