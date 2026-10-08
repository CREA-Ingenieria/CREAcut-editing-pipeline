; Run in the installing user's account so Whisper and Ollama share its caches.
!macro customInstallMode
  StrCpy $isForceCurrentInstall "1"
!macroend

!define CREACUT_PS "$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
!define CREACUT_VENV_PYTHON "$LOCALAPPDATA\CREAcut\runtime\.venv\Scripts\python.exe"

!macro customUnInstall
  ; electron-builder also runs this hook when replacing an installation.
  ${IfNot} ${isUpdated}
    ${IfNot} ${Silent}
      MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "Eliminar tambien los modelos Whisper y Gemma de CREAcut?$\n$\nSe borraran Whisper large-v3, Whisper medium y Gemma 4 (gemma4:latest). Otras aplicaciones pueden usar estos mismos modelos.$\n$\nSe conservaran los demas modelos, Ollama, tus videos y proyectos." /SD IDNO IDNO creacut_keep_models
      SetDetailsView show
      ; Embed the helper in the uninstaller, independent of installed files/Python.
      InitPluginsDir
      File /oname=$PLUGINSDIR\remove-models.ps1 "${BUILD_RESOURCES_DIR}\remove-models.ps1"
      DetailPrint "Eliminando los modelos seleccionados..."
      nsExec::ExecToLog '"${CREACUT_PS}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\remove-models.ps1"'
      Pop $0
      ${If} $0 != 0
        MessageBox MB_OK|MB_ICONEXCLAMATION "No se pudieron eliminar todos los modelos. Revisa los detalles.$\n$\nSi fallo Gemma, abre Ollama y ejecuta: ollama rm gemma4:latest$\n$\nLa desinstalacion de CREAcut continuara." /SD IDOK
      ${EndIf}
      creacut_keep_models:
    ${EndIf}
  ${EndIf}
!macroend

!macro customInstall
  SetDetailsView show

  ; El backend ya no viaja dentro del EXE: se construye aqui desde PyPI. Por eso
  ; la descarga es pequena y la instalacion necesita Internet.
  DetailPrint "Preparando el backend de CREAcut. Se requiere Internet."
  creacut_backend_retry:
    nsExec::ExecToLog '"${CREACUT_PS}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\resources\backend-setup\install-backend.ps1" -InstallDirectory "$INSTDIR"'
    Pop $0
    ${If} $0 != 0
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "No se pudo instalar el backend. Comprueba la conexion a Internet y el espacio libre. Revisa los detalles antes de reintentar." /SD IDCANCEL IDRETRY creacut_backend_retry
      SetErrorLevel 1
      Abort "La instalacion del backend quedo incompleta."
    ${EndIf}

  ; El paquete CUDA solo se ofrece si hay controlador NVIDIA. Son ~3,7 GB que no
  ; aportan nada sin GPU compatible, asi que nunca se instala por defecto.
  IfFileExists "$WINDIR\Sysnative\nvidia-smi.exe" 0 creacut_models
    MessageBox MB_YESNO|MB_ICONQUESTION "Se detecto una GPU NVIDIA.$\n$\nPuedes anadir el paquete CUDA para acelerar la transcripcion. Ocupa unos 3,7 GB adicionales.$\n$\nSin el, CREAcut transcribe con el procesador.$\n$\n?Instalar el paquete CUDA ahora?" /SD IDNO IDNO creacut_models
    DetailPrint "Instalando el paquete CUDA. Puede tardar varios minutos."
    nsExec::ExecToLog '"${CREACUT_PS}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\resources\backend-setup\install-gpu-pack.ps1"'
    Pop $0
    ${If} $0 != 0
      ; No es motivo para abortar: el backend CPU instalado sigue sirviendo.
      MessageBox MB_OK|MB_ICONEXCLAMATION "No se pudo instalar el paquete CUDA. CREAcut funcionara con el procesador.$\n$\nPuedes reintentarlo mas tarde ejecutando install-gpu-pack.ps1 desde la carpeta de instalacion." /SD IDOK
    ${EndIf}

  creacut_models:
  DetailPrint "Preparando Whisper y Gemma 4. Se requiere Internet."
  creacut_models_retry:
    nsExec::ExecToLog '"${CREACUT_VENV_PYTHON}" "$INSTDIR\resources\backend\python\setup_models.py"'
    Pop $0
    ${If} $0 != 0
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "No se pudieron preparar los modelos. Revisa los detalles, la conexion y el espacio disponible. Reintentar reutiliza las descargas completas." /SD IDCANCEL IDRETRY creacut_models_retry
      SetErrorLevel 1
      Abort "La preparacion de modelos quedo incompleta. Ejecuta de nuevo el instalador."
    ${EndIf}
!macroend
