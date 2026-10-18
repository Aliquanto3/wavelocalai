@echo off
rem Ouvre la maquette de WaveLocalAI v2 : petit serveur local sur un port libre, puis le navigateur.
rem Fermer cette fenetre arrete le serveur.
cd /d "%~dp0"
where py >nul 2>nul && (py -3 serveur.py & goto :fin)
where python >nul 2>nul && (python serveur.py & goto :fin)
echo Python 3 est introuvable. Installez-le depuis python.org, puis relancez ouvrir.cmd.
pause
:fin
