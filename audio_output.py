import os
import time
import yaml
import shutil
from pathlib import Path
from elevenlabs import ElevenLabs, VoiceSettings
import subprocess
import signal

class AudioPlayback:
    """Clase para reproducir texto como audio usando ElevenLabs."""

    def __init__(self, config_path=None):
        """Inicializa el cliente de ElevenLabs y verifica ffplay."""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        
        # Forzar el PATH para incluir FFmpeg
        ffmpeg_path = r"C:\ffmpeg\bin"  # Ajusta esta ruta según tu instalación
        os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ["PATH"]
        print(f"DEBUG: PATH actualizado = {os.environ['PATH']}")

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["elevenlabs"]

        self.api_key = config["api_key"]
        self.voice_id = config["voice_id"]
        self.client = ElevenLabs(api_key=self.api_key)

        # Verificar ffplay
        self.ffplay_path = shutil.which("ffplay")
        if self.ffplay_path:
            print(f"✅ ffplay detectado en: {self.ffplay_path}")
        else:
            print("🚨 ERROR: ffplay no detectado. Asegúrate de que FFmpeg está instalado y en el PATH.")
        
        self.active_processes = []  # Lista para rastrear todos los procesos FFmpeg activos

    def play(self, text):
        """Convierte el texto en audio con ElevenLabs y lo reproduce con ffplay."""
        print(f"Intentando reproducir: '{text}'")
        if not self.ffplay_path:
            print("❌ Error: ffplay no está disponible. Instala FFmpeg y agrégalo al PATH.")
            return

        try:
            # Detener todas las reproducciones anteriores
            self.stop()

            # Pausa si contiene "Déjame revisar"
            if "Déjame revisar" in text:
                print("⏳ Pausa de 2 segundos antes de la oferta...")
                time.sleep(2)

            # Generar audio desde ElevenLabs
            print("🎤 Generando audio con ElevenLabs...")
            audio_stream = self.client.generate(
                text=text,
                voice=self.voice_id,
                model="eleven_multilingual_v2",
                voice_settings=VoiceSettings(
                    speed=1.1,
                    stability=0.5,
                    similarity_boost=0.8
                )
            )

            # Convertir el stream a bytes
            print("🔄 Convirtiendo stream a bytes...")
            audio_bytes = b"".join(audio_stream)
            print(f"📦 Audio generado, tamaño en bytes: {len(audio_bytes)}")

            if len(audio_bytes) == 0:
                print("❌ Error: No se generó audio (audio_bytes vacío)")
                return

            # Reproducir con ffplay manualmente
            print("🔊 Reproduciendo audio con ffplay...")
            process = subprocess.Popen(
                [self.ffplay_path, "-nodisp", "-autoexit", "-i", "pipe:0"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            process.stdin.write(audio_bytes)
            process.stdin.flush()
            process.stdin.close()
            self.active_processes.append(process)
            print("✅ Reproducción iniciada.")

            # Limpiar procesos terminados
            self._cleanup_processes()

        except Exception as e:
            print(f"❌ Error al reproducir con ElevenLabs: {e}")
            import traceback
            traceback.print_exc()

    def stop(self):
        """Detiene todas las reproducciones activas de ffplay de manera robusta."""
        if self.active_processes:
            print("🛑 Deteniendo todas las reproducciones anteriores...")
            for process in self.active_processes:
                if process.poll() is None:  # Si el proceso está activo
                    try:
                        process.kill()  # Usar kill() para una terminación más agresiva
                        process.wait(timeout=1)  # Esperar con límite de tiempo
                    except subprocess.TimeoutExpired:
                        print(f"⚠️ Proceso {process.pid} no terminó a tiempo, forzando con taskkill...")
                        os.system(f"taskkill /PID {process.pid} /F")  # Forzar en Windows
            self.active_processes.clear()
            print("✅ Todas las reproducciones detenidas.")

        # Doble verificación: matar todos los ffplay.exe en Windows
        print("🔍 Verificando y eliminando cualquier ffplay residual...")
        os.system("taskkill /IM ffplay.exe /F >nul 2>&1")  # Silencioso, fuerza la terminación de todos los ffplay

    def _cleanup_processes(self):
        """Elimina los procesos que ya terminaron de la lista."""
        self.active_processes = [p for p in self.active_processes if p.poll() is None]

    def close(self):
        """Cierra recursos."""
        self.stop()  # Detener todas las reproducciones
        print("🛑 Cierre de AudioPlayback completado.")