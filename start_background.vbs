Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get directory of this VBScript
curDir = fso.GetParentFolderName(WScript.ScriptFullName)

' 1. Check if port 8765 is already listening to avoid duplicate processes
Set oExec = WshShell.Exec("cmd /c netstat -ano | findstr 127.0.0.1:8765 | findstr LISTENING")
sOutput = oExec.StdOut.ReadAll()
If Len(Trim(sOutput)) > 0 Then
    ' Server already running, exit silently without error or window
    WScript.Quit 0
End If

' 2. Locate portable python interpreter (prefer pythonw.exe to prevent console flashes)
pyExe = ""
If fso.FileExists(curDir & "\.venv\Scripts\pythonw.exe") Then
    pyExe = curDir & "\.venv\Scripts\pythonw.exe"
ElseIf fso.FileExists(curDir & "\.venv\Scripts\python.exe") Then
    pyExe = curDir & "\.venv\Scripts\python.exe"
Else
    pyExe = "python.exe"
End If

' 3. Ensure workspace directory exists for server.log
wsDir = curDir & "\workspace"
If Not fso.FolderExists(wsDir) Then
    fso.CreateFolder(wsDir)
End If

logFile = wsDir & "\server.log"
cmdLine = "cmd /c cd /d """ & curDir & """ && """ & pyExe & """ -m uvicorn server.app:app --host 127.0.0.1 --port 8765 >> """ & logFile & """ 2>&1"

' 4. Launch completely hidden (0 = hide window, False = don't wait for termination)
WshShell.Run cmdLine, 0, False
