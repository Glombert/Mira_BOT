# tools/ — инструменты агента
# Импортируем всё в одном месте, чтобы в agent.py писать просто:
# from tools import list_files, read_file, write_file, run_python

from tools.file_tools    import list_files, read_file, write_file, undo_last, list_undo
from tools.shell_tools   import run_python
from tools.excel_tools   import excel_read, excel_write
from tools.search_tools  import web_search
