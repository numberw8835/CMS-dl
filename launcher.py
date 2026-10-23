"""Entry point of the Linux AppImage: the window when started without arguments, the command line otherwise.

Started through a link named cms-dl (ln -s CMS-Downloader.AppImage ~/.local/bin/cms-dl), it is
always the command line, so `cms-dl --sync` works like `python main.py --sync`.
"""
import multiprocessing
import os
import sys


def wants_command_line():
    invoked_as = os.path.basename(os.environ.get("ARGV0") or sys.argv[0])  # the AppImage runtime sets ARGV0
    if os.path.splitext(invoked_as)[0].lower() == "cms-dl" or len(sys.argv) > 1:
        return True
    return sys.platform.startswith("linux") and not os.environ.get("DISPLAY")  # no screen for a window


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if wants_command_line():
        from main import main
    else:
        from gui_modules import main
    main()
