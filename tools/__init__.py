# tools/ — инструменты агента
# Импортируем всё в одном месте, чтобы в agent.py писать просто:
# from tools import list_files, read_file, write_file, run_python

from tools.file_tools    import list_files, read_file, write_file, undo_last, list_undo
from tools.shell_tools   import run_python
from tools.excel_tools   import excel_read, excel_write
from tools.search_tools  import web_search
from tools.self_tools       import list_self, read_self, git_log
from tools.self_write_tools import write_persona, write_agent_config
from tools.gdrive_tools import gdrive_list, gdrive_read, gdrive_write, is_authorized, auto_upload_to_drive, gdrive_status
from tools.gdrive_tools import gcal_list, gcal_create, gcal_quick_add
from tools.gdrive_tools import gsheet_read, gsheet_write, gsheet_create
from tools.metrics_tools import metrics_read
