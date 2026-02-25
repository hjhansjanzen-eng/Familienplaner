Dim fso, shell, dir
Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run "pythonw """ & dir & "\schulmanager_proxy.py""", 0, False
