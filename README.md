# Hadoop Battle Arena — torneo multijugador

Juego educativo en Flask + Flask-SocketIO con fondo de arena y personajes incluidos. El servidor asigna el avatar a cada participante y todos los navegadores ven el mismo personaje. Los rivales se sortean por parejas en cada ronda; un jugador solo puede atacar a su rival asignado. El ganador de cada combate avanza y las vidas se reinician al comenzar la siguiente ronda.

## Ejecutar en Windows
1. Instala Python 3.10+ desde https://www.python.org/downloads/ y activa “Add Python to PATH”.
2. Descomprime el ZIP.
3. Abre CMD en la carpeta del proyecto.
4. Ejecuta:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
5. Abre http://127.0.0.1:5000.

## Anfitrión
Pulsa el botón **ANFITRIÓN** y usa el PIN configurado. El valor local por defecto es `1234`; no lo uses en internet. En el panel puedes iniciar, avanzar pregunta/ronda y reiniciar la sala. Cada ronda se avanza con “Siguiente pregunta”; cuando todos los combates tienen ganador, el siguiente clic forma las nuevas parejas. Con 16 jugadores se generan 8 combates, luego 4, 2 y la gran final.

## Publicar en Render
1. Crea un repositorio en GitHub y sube el contenido de esta carpeta (no subas `.venv`).
2. En Render elige **New → Blueprint** y conecta ese repositorio; Render leerá `render.yaml`. También puedes crear un Web Service con Build command `pip install -r requirements.txt` y Start command `python app.py`.
3. En Environment configura `HOST_PIN` con un PIN privado y `SECRET_KEY` con una cadena larga aleatoria.
4. Despliega y comparte la URL HTTPS de Render con los participantes.
5. Prueba primero con 3–4 dispositivos y luego con los 16. Mantén una sola instancia del servicio porque el estado de la sala está en memoria.

## Límites importantes
- El estado se almacena en memoria; si Render reinicia el servicio, se pierde la partida.
- Para este prototipo, una respuesta correcta habilita un golpe de 20 de daño. Las parejas son aleatorias en cada ronda.
- El desempate por pregunta extra todavía debe agregarse si se decide finalizar combates por límite de tiempo o por puntos iguales; con el sistema actual el combate termina por KO (vidas en cero).
- Los personajes se asignan desde el servidor y se sincronizan entre participantes. Si una misma persona abre dos navegadores y entra dos veces con apodos diferentes, el sistema los trata como dos jugadores diferentes.
