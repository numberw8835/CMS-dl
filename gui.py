"""Starts the GUC CMS Downloader window: python gui.py"""
import multiprocessing

from gui_modules import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
