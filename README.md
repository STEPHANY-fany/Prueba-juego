# Hadoop Battle Arena — torneo multijugador

Juego educativo en Flask + Flask-SocketIO con fondo de arena y personajes incluidos. El servidor asigna el avatar a cada participante y todos los navegadores ven el mismo personaje. Los rivales se sortean por parejas en cada ronda; cada acierto golpea solo al rival asignado. El ganador de cada combate avanza y las vidas se reinician al comenzar la siguiente ronda.

## Cómo se juega
- Cada jugador entra con un apodo. El **anfitrión también entra como jugador** y después activa el modo anfitrión con el botón **ANFITRIÓN** y el PIN.
- El anfitrión pulsa **Iniciar partida**: se forman las parejas al azar. Con un número impar de jugadores, uno descansa (*bye*) y pasa directo; el descanso va primero a quien todavía no ha descansado.
- Todos reciben la misma pregunta y tienen **20 segundos** para responder (una barra y una cuenta atrás lo muestran). Quien acierta golpea a su rival al instante, sin pulsar nada (20 de daño); con 5 golpes hay KO y el ganador avanza. Quien no responde a tiempo no golpea. Quien ya ganó **espera a que terminen los demás combates**; la pantalla le indica cuántos faltan.
- **El juego avanza solo, no hay botón de "siguiente".** La pregunta se cierra al vencer los 20 s, o antes si ya respondieron todos los que pueden responder. Entonces se muestra durante 6 segundos un **resumen**: la respuesta correcta, el ranking con las flechas ▲▼ de lo que cambió y los KO de esa pregunta. Después llega la pregunta siguiente.
- Cuando todos los combates tienen ganador, la siguiente pregunta forma sola las nuevas parejas. Con 16 jugadores se juegan 8 combates, luego 4, 2 y la gran final. El campeón se anuncia solo al terminar la final, con el podio de los 3 primeros.

## Ranking
El panel de la **izquierda** muestra a los 3 primeros con 🏆 🥈 🥉, si siguen **vivos** o están **eliminados** y sus puntos; si no estás entre ellos, debajo ves tu posición. Los puntos se acumulan durante todo el torneo:
- **+10** por cada acierto (cada golpe).
- **+50** por ganar un combate (por KO, abandono del rival o decisión del anfitrión). El descanso no suma.
- Desempate: más victorias, luego más aciertos, luego el nombre. Un jugador eliminado puede seguir entre los 3 primeros.
- **El campeón es quien gana la final, y no tiene por qué ser el primero del ranking**: alguien eliminado antes puede haber acumulado más puntos. Por eso el podio final se titula "Ranking final por puntos" y se muestra debajo del nombre del campeón.

## Si alguien se desconecta
- **Recargar la página (F5) o perder el Wi-Fi no saca al jugador:** al volver recupera su lugar, su vida y su combate. Si cerró la pestaña, basta con entrar de nuevo con **el mismo apodo**.
- Si no vuelve en 45 segundos (configurable con `RECONNECT_GRACE_SECONDS`): en el lobby se le saca de la lista; en pleno torneo su rival gana el combate por abandono.
- Si se caen **los dos** de un combate, avanza el que tenga más vida (o uno al azar).
- Si algún combate se trabó por otra causa, el panel del anfitrión lista los **Combates pendientes** con un botón **Gana …** por jugador para decidirlo a mano. Los jugadores sin conexión aparecen marcados con 📴.
- Dos jugadores **conectados pero inactivos** en el mismo combate no se resuelven solos: las preguntas siguen pasando por tiempo, pero ese combate no termina hasta que el anfitrión pulse **Gana …**.

## Torneo en red local (LAN)
1. En el equipo que será el servidor instala Python 3.10+ desde https://www.python.org/downloads/ (con “Add Python to PATH”).
2. Haz doble clic en **`iniciar_lan.bat`**. La primera vez crea el entorno virtual e instala las dependencias; después te pide el PIN (Enter = `1234`) y arranca.
3. La ventana muestra dos direcciones. El anfitrión usa `http://127.0.0.1:5000`; **los demás jugadores escriben la de “En la red local”** (por ejemplo `http://192.168.1.50:5000`) en su navegador.
4. Todos deben estar en la misma red. Si no pueden entrar, abre el puerto en el Firewall de Windows (una sola vez, desde un CMD **como administrador**):
   ```bat
   netsh advfirewall firewall add rule name="Hadoop Battle Arena" dir=in action=allow protocol=TCP localport=5000
   ```
5. No necesita internet: el cliente de Socket.IO viene incluido en `static/` (las fuentes de Google, si no hay internet, se sustituyen por las del sistema).

Para ejecutarlo a mano en lugar del `.bat`:
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Torneo en Render (internet)
1. Sube el contenido de esta carpeta a un repositorio de GitHub (no subas `.venv` ni `.env`; ya están en `.gitignore`).
2. En Render elige **New → Blueprint** y conecta el repositorio; Render leerá `render.yaml`. También sirve un Web Service con Build command `pip install -r requirements.txt` y Start command `python app.py`. La versión de Python se toma de `.python-version`.
3. En **Environment** revisa `HOST_PIN` (y `SECRET_KEY`).
4. Despliega y comparte la URL HTTPS con los participantes.
5. **Mantén una sola instancia**: el estado de la sala está en memoria y no se comparte entre instancias.
6. Antes del torneo abre la URL unos minutos antes: en el plan *free* el servicio se “duerme” tras un rato sin visitas y tarda en arrancar. Haz una prueba con 3–4 dispositivos.

## Configuración (opcional)
Copia `.env.example` como `.env` para cambiar el PIN, el puerto o el plazo de reconexión. En Render se definen como variables de entorno.

| Variable | Por defecto | Qué hace |
|---|---|---|
| `HOST_PIN` | `1234` | PIN del anfitrión |
| `PORT` | `5000` | Puerto del servidor |
| `RECONNECT_GRACE_SECONDS` | `45` | Espera antes de dar por perdido a quien se desconectó |
| `QUESTION_SECONDS` | `20` | Tiempo para responder cada pregunta |
| `REVIEW_SECONDS` | `6` | Duración del resumen del ranking entre preguntas |
| `SECRET_KEY` | `cambia-esta-clave` | Clave de Flask (solo importa si publicas en internet) |

## Probar antes del torneo (opcional)
`tools/prueba_carga.py` simula jugadores reales (incluidas recargas de página, jugadores que desaparecen y jugadores conectados que no responden) y comprueba que el torneo siempre termina con un campeón, que cada pregunta cierra a tiempo y que el ranking sale ordenado. Con `--spawn` usa preguntas de pocos segundos para no tardar:
```bat
pip install -r requirements-dev.txt
python tools\prueba_carga.py --spawn --players 20
python tools\prueba_carga.py --spawn --players 20 --reload-mid 4 --vanish 3
python tools\prueba_carga.py --spawn --players 20 --vanish-pair
python tools\prueba_carga.py --spawn --players 20 --afk 4 --question-seconds 2
python tools\prueba_carga.py --spawn --players 20 --afk-pair
python tools\prueba_carga.py --url http://192.168.1.50:5000 --players 20
```
Con `--url` usa un servidor ya en marcha (ojo: lo llena de jugadores de prueba; reinicia la sala después).

## Límites importantes
- El estado se almacena en memoria; si el servicio se reinicia, se pierde la partida.
- Una respuesta correcta golpea automáticamente con 20 de daño y las parejas son aleatorias en cada ronda.
- Si los dos rivales aciertan y llegan al KO en la misma pregunta, gana quien responda primero (según llegue su respuesta al servidor). El desempate por pregunta extra o por tiempo todavía no existe.
- Los personajes se asignan al azar desde el servidor y pueden repetirse entre jugadores.
- Si una misma persona abre dos navegadores y entra dos veces con apodos diferentes, el sistema los trata como dos jugadores diferentes.
