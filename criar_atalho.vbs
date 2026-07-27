' Cria o atalho "Painel MAPA" na area de trabalho (com icone proprio).
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName) & "\"
desktop = sh.SpecialFolders("Desktop")
Set atalho = sh.CreateShortcut(desktop & "\Painel MAPA.lnk")
atalho.TargetPath = "wscript.exe"
atalho.Arguments = """" & pasta & "iniciar_painel.vbs"""
atalho.WorkingDirectory = pasta
If fso.FileExists(pasta & "painel.ico") Then
  atalho.IconLocation = pasta & "painel.ico"
End If
atalho.Description = "Painel de exames MAPA"
atalho.Save
WScript.Echo "Atalho criado em: " & desktop & "\Painel MAPA.lnk"
