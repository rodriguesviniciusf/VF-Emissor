Option Explicit
Dim shell, fso, folder, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
command = Chr(34) & folder & "\portable\python.exe" & Chr(34) & " " & Chr(34) & folder & "\desktop_launcher.py" & Chr(34)
shell.Run command, 7, False
