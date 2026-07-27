' Vatican Browser Agent — runs silently in background
' Place this in Windows Startup folder to auto-start
Dim fso, scriptDir
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

Set WshShell = CreateObject("WScript.Shell")
' Run python agent with no window (0 = hidden)
WshShell.Run "python """ & scriptDir & "\backend\local_browser_agent.py""", 0, False
