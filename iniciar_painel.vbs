' Abre o Painel MAPA sem janela preta.
' Se o painel ja estiver aberto, so abre o navegador de novo.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
On Error Resume Next
sh.Run "pyw iniciar.py", 0, False
If Err.Number <> 0 Then
  Err.Clear
  ' sem o pyw, abre com janela mesmo (melhor que nao abrir)
  sh.Run "py iniciar.py", 1, False
  If Err.Number <> 0 Then
    MsgBox "Nao encontrei o Python neste computador." & vbCrLf & _
           "Instale em python.org e tente de novo.", 48, "Painel MAPA"
  End If
End If
