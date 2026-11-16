"""Spanish / English text. T("English text") returns the text in the chosen language."""
import settings

LANG = settings.load().get("lang") or "es"

ES = {
    # menu
    "File": "Archivo",
    "New session": "Nueva sesión",
    "Open session…": "Abrir sesión…",
    "Save session": "Guardar sesión",
    "Save session as…": "Guardar sesión como…",
    "Language…": "Idioma…",
    "About": "Acerca de",
    "About…": "Acerca de…",
    "Language": "Idioma",
    "Theme": "Tema",
    "Changing the theme requires restarting the app.": "El cambio de tema requiere reiniciar la aplicación.",
    "Saved. Close the app and open it again to apply the new theme.":
        "Guardado. Cierra la aplicación y ábrela de nuevo para aplicar el nuevo tema.",
    "Changing the language requires restarting the app.":
        "El cambio de idioma requiere reiniciar la aplicación.",
    "Saved. Close the app and open it again to apply the new language.":
        "Guardado. Cierra la aplicación y ábrela de nuevo para aplicar el nuevo idioma.",
    "vibe coded by jc": "vibe coded por jc",
    "OK": "OK",
    # header / left column
    "1. WHAT TO DOWNLOAD": "1. QUÉ DESCARGAR",
    "Convert playlist": "Convertir playlist",
    "Song list": "Lista de canciones",
    "Turn any playlist into text with TuneMyMusic": "Pasa tu playlist a texto con TuneMyMusic",
    "Open TuneMyMusic": "Abrir TuneMyMusic",
    "Open TuneMyMusic and select your service": "Abre TuneMyMusic y elige tu servicio",
    "Paste the playlist URL (log in to your account if necessary)":
        "Pega la URL de la playlist (inicia sesión en tu cuenta si es necesario)",
    "Click Choose destination": "Haz clic en Elegir destino",
    "Select Export to file at the bottom": "Selecciona Exportar a archivo, abajo",
    "Copy the contents of your text file": "Copia el contenido de tu archivo de texto",
    " here": " aquí",
    "“here” takes you to the Song list tab. Paste with Ctrl+V.":
        "“aquí” abre Lista de canciones. Pega con Ctrl+V.",
    "Paste your songs, one per line, as Artist - Title":
        "Pega tus canciones, una por línea, como Artista - Título",
    "No limit on length.": "Sin límite de largo.",
    "Find": "Buscar",
    "Max active dl:": "Max dl activas:",
    "Cut": "Cortar", "Copy": "Copiar", "Paste": "Pegar", "Select all": "Seleccionar todo",
    "2. SESSION NAME (REQUIRED)": "2. NOMBRE DE LA SESIÓN (OBLIGATORIO)",
    "Browse…": "Examinar…",
    "Saves to: ": "Se guarda en: ",
    "<session name>": "<nombre de la sesión>",
    "Finished files are saved as: 0001 - Artist - Album - Track.":
        "Los archivos terminados se guardan como: 0001 - Artista - Álbum - Canción.",
    "3. QUALITY": "3. CALIDAD",
    "Best quality (FLAC first, then MP3 320)": "Mejor calidad (primero FLAC, luego MP3 320)",
    "Boomer mode (MP3 only, ignores FLAC)": "Modo boomer (solo MP3, ignora FLAC)",
    "Only FLAC and MP3 are used. FLAC 16/44.1 is preferred; higher only if it’s the only FLAC. "
    "MP3 320 is preferred; V0 only if there’s no 320. V1, V2, 256 and 192 ask for your OK first.":
        "Solo se usan FLAC y MP3. Se prefiere FLAC 16/44.1; una calidad mayor solo si es el único FLAC. "
        "Se prefiere MP3 320; V0 solo si no hay 320. V1, V2, 256 y 192 piden tu OK antes.",
    "Start download": "Iniciar descarga",
    "Starting…": "Iniciando…",
    "Running…": "Descargando…",
    # right column
    "QUEUE": "COLA",
    "QUEUE · {:,} songs": "COLA · {:,} canciones",
    "Nothing running yet.": "Aún no hay nada en marcha.",
    "Filter:": "Filtrar:",
    "Song": "Canción", "Details": "Detalles", "Status": "Estado",
    "Download anyway": "Descargar igual",
    "Skip": "Omitir",
    "Search again": "Buscar de nuevo",
    "Open session folder": "Abrir carpeta de la sesión",
    "Stop": "Detener",
    "{:,} done": "{:,} listas",
    "%d active": "%d activas",
    "{:,} waiting in line": "{:,} en espera",
    "%d not found": "%d no encontradas",
    "%d need your OK": "%d necesitan tu OK",
    # login popup
    "Enter a Soulseek username and password first.": "Primero escribe un usuario y una contraseña de Soulseek.",
    "SOULSEEK USERNAME": "USUARIO DE SOULSEEK",
    "No sign-up needed: a new name is created the first time you log in.":
        "No necesitas registrarte: el usuario se crea la primera vez que inicias sesión.",
    "SOULSEEK PASSWORD": "CONTRASEÑA DE SOULSEEK",
    "Save": "Guardar",
    # dialogs and messages
    "The session folder doesn't exist yet. It's created when you start.":
        "La carpeta de la sesión todavía no existe. Se crea cuando inicias la descarga.",
    "Downloads are still running. Stop them and start a new session?":
        "Aún hay descargas en curso. ¿Detenerlas y empezar una sesión nueva?",
    "Start a new session? Unsaved changes to this one will be lost (use File > Save session first to keep it).":
        "¿Empezar una sesión nueva? Los cambios sin guardar de esta se perderán "
        "(usa Archivo > Guardar sesión antes para conservarla).",
    "Couldn't save the session: %s": "No se pudo guardar la sesión: %s",
    "Save session ": "Guardar sesión ",
    "SLSK session": "Sesión SLSK",
    "All files": "Todos los archivos",
    "Open session": "Abrir sesión",
    "Press Stop first, then open a session.": "Primero pulsa Detener y luego abre una sesión.",
    "That isn't a session file from this app.": "Ese no es un archivo de sesión de esta aplicación.",
    "Couldn't open that file: %s": "No se pudo abrir ese archivo: %s",
    "Session loaded. Press Start to continue.": "Sesión cargada. Pulsa Iniciar descarga para continuar.",
    "There are no songs yet. Follow the steps in Convert playlist, or paste songs into the Song list tab.":
        "Todavía no hay canciones. Sigue los pasos de Convertir playlist o pega canciones en la pestaña Lista de canciones.",
    "Give this session a name first. It becomes the folder name.":
        "Primero ponle un nombre a la sesión. Será el nombre de la carpeta.",
    "Downloads are still running. Stop and close?\nYou can continue later with the same session name.":
        "Aún hay descargas en curso. ¿Detener y cerrar?\nPuedes continuar después con el mismo nombre de sesión.",
    "Stopped. Press Start to continue where you left off.":
        "Detenido. Pulsa Iniciar descarga para continuar donde te quedaste.",
    "All done.": "Todo listo.",
    "Soulseek: connected as ": "Soulseek: conectado como ",
    "  (%d already done)": "  (%d ya listas)",
    "First run: downloading the Soulseek engine…": "Primera vez: descargando el motor de Soulseek…",
    "Downloading Soulseek engine: %d%%": "Descargando el motor de Soulseek: %d%%",
    "Logging in to Soulseek…": "Conectando a Soulseek…",
    "No songs were found in that.": "No se encontraron canciones en ese texto.",
    "Where should the session folder be created?": "¿Dónde se debe crear la carpeta de la sesión?",
    # queue status / details
    "Place: %s": "Lugar: %s",
    "Downloading %d%%": "Descargando %d%%",
    "Low quality only": "Solo baja calidad",
    "Queued": "En cola", "Searching": "Buscando", "Not found": "No encontrada", "Done": "Lista",
    "Skipped": "Omitida",
    "%s  |  Saved as: %s": "%s  |  Guardada como: %s",
    "%s, searching again in %d min": "%s, buscando de nuevo en %d min",
    "No matching files": "No hay archivos que coincidan",
    "%s from %s. Waiting for your OK, searching for better in %d min":
        "%s de %s. Esperando tu OK, buscando algo mejor en %d min",
    "%s from %s, starts automatically when a slot opens":
        "%s de %s, empieza solo cuando se libere un lugar",
    "Skipped by you": "Omitida por ti",
    "Trying another source": "Probando otra fuente",
    "Best found: %s from %s. Not downloading until you say so.":
        "Mejor encontrada: %s de %s. No se descarga hasta que lo autorices.",
    "Search error": "Error de búsqueda",
    "FLAC (high resolution)": "FLAC (alta resolución)",
    # engine notices / errors
    "The Soulseek engine keeps stopping. Check that Windows Firewall or your antivirus isn't blocking slskd.exe.":
        "El motor de Soulseek se sigue deteniendo. Revisa que el Firewall de Windows o tu antivirus no bloqueen slskd.exe.",
    "Disconnected from Soulseek. Reconnecting…": "Desconectado de Soulseek. Reconectando…",
    "Soulseek engine unavailable. Retrying in %d s…": "Motor de Soulseek no disponible. Reintentando en %d s…",
    "Soulseek engine stopped, restarting…": "El motor de Soulseek se detuvo, reiniciando…",
    "Couldn't restart the Soulseek engine. Press Stop, then Start download.":
        "No se pudo reiniciar el motor de Soulseek. Pulsa Detener y luego Iniciar descarga.",
    "The Soulseek engine closed unexpectedly. ": "El motor de Soulseek se cerró inesperadamente. ",
    "The Soulseek engine didn't start. ": "El motor de Soulseek no arrancó. ",
    "(Is Windows Firewall or an antivirus blocking 'slskd.exe' in the data folder?)":
        "(¿El Firewall de Windows o un antivirus están bloqueando 'slskd.exe' en la carpeta de datos?)",
    "Couldn't log in to Soulseek. If this username already exists, the password must match it; "
    "otherwise pick a different username in Soulseek login.":
        "No se pudo iniciar sesión en Soulseek. Si ese usuario ya existe, la contraseña debe coincidir; "
        "si no, elige otro usuario en Soulseek login.",
    "Couldn't download the Soulseek engine (%s). Check your internet connection and that GitHub isn't blocked, then try again.":
        "No se pudo descargar el motor de Soulseek (%s). Revisa tu conexión a internet y que GitHub no esté bloqueado, e inténtalo de nuevo.",
    "The Soulseek engine download looks incomplete. Delete the 'data' folder and try again.":
        "La descarga del motor de Soulseek parece incompleta. Borra la carpeta 'data' e inténtalo de nuevo.",
}


def T(text):
    return ES.get(text, text) if LANG == "es" else text
