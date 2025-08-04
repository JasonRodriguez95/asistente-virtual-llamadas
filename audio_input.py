import asyncio
import pyaudio
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
import yaml
from pathlib import Path
import sys
import threading
import queue
import tkinter as tk
from tkinter import scrolledtext

# Añade la raíz del proyecto al path de Python
sys.path.append(str(Path(__file__).parent.parent))

from src.llm_processor import LLMProcessor
from src.audio_output import AudioPlayback

class TranscriptionWindow:
    """Ventana secundaria para mostrar transcripciones en tiempo real."""
    def __init__(self, transcript_queue):
        self.queue = transcript_queue
        self.root = tk.Tk()
        self.root.title("Transcripciones de Deepgram")
        self.root.geometry("400x300")
        self.root.configure(bg="#0d1b2a")  # Color de fondo de la ventana
        
        self.text_area = scrolledtext.ScrolledText(
            self.root, 
            wrap=tk.WORD, 
            width=40, 
            height=20, 
            bg="#0d1b2a",  # Color de fondo del área de texto
            fg="#ffffff",  # Color del texto blanco para contraste
            insertbackground="#ffffff"  # Color del cursor
        )
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        self.running = True
        self.update_thread = threading.Thread(target=self.update_text)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

    def update_text(self):
        """Actualiza la ventana con las transcripciones de la cola."""
        while self.running:
            try:
                transcript = self.queue.get(timeout=0.1)
                if transcript is None:
                    break
                self.text_area.insert(tk.END, f"{transcript}\n")
                self.text_area.see(tk.END)
            except queue.Empty:
                continue

    def on_closing(self):
        """Cierra la ventana limpiamente."""
        self.running = False
        self.root.destroy()

class AudioInput:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        deepgram_config = config["deepgram"]
        self.api_key = deepgram_config["api_key"]
        self.deepgram = DeepgramClient(self.api_key)
        self.dg_connection = self.deepgram.listen.websocket.v("1")

        audio_config = config["audio"]
        self.chunk = audio_config["chunk"]
        self.format = getattr(pyaudio, audio_config["format"])
        self.channels = audio_config["channels"]
        self.rate = audio_config["rate"]
        self.device_id = audio_config["device_id"]

        self.llm = LLMProcessor(config_path)
        self.playback = AudioPlayback(config_path)

        self.transcript_queue = queue.Queue()

        self.transcript_window_thread = threading.Thread(
            target=TranscriptionWindow, args=(self.transcript_queue,)
        )
        self.transcript_window_thread.daemon = True
        self.transcript_window_thread.start()

        self.audio = None
        self.stream = None

    def _configure_transcription_options(self):
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["deepgram"]
        return LiveOptions(
            model=config["model"],
            language=config["language"],
            smart_format=config["smart_format"],
            encoding="linear16",
            sample_rate=self.rate
        )

    def _on_transcript(self, sender, result, **kwargs):
        if result.channel and result.channel.alternatives:
            transcript = result.channel.alternatives[0].transcript
            if transcript:
                self.transcript_queue.put(transcript)
                self.playback.stop()
                threading.Thread(target=self._process_transcript, args=(transcript,)).start()

    def _process_transcript(self, transcript):
        print(f"Transcripción: {transcript}")
        response = self.llm.process(transcript)
        print(f"Respuesta de Grok: {response}")
        self.playback.play(response)

    def _setup_deepgram(self):
        self.dg_connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
        options = self._configure_transcription_options()
        self.dg_connection.start(options)
        print("🔗 Conexión con Deepgram establecida.")

    def _setup_audio(self):
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=self.device_id,
            frames_per_buffer=self.chunk
        )
        print("🎤 Micrófono iniciado...")

    async def start(self):
        self._setup_deepgram()
        self._setup_audio()
        print("🎤 Habla al micrófono... (Ctrl+C para detener)")
        try:
            while True:
                data = self.stream.read(self.chunk, exception_on_overflow=False)
                self.dg_connection.send(data)
                await asyncio.sleep(0.01)
        except KeyboardInterrupt:
            await self.stop()

    async def stop(self):
        if self.dg_connection:
            await self.dg_connection.finish()
            print("🔗 Conexión con Deepgram cerrada.")
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()
            print("🎤 Micrófono detenido.")
        self.playback.close()
        self.transcript_queue.put(None)
        self.transcript_window_thread.join(timeout=1)
        print("📌 Ventana de transcripciones detenida.")
        print("\n📌 Transcripción detenida.")

async def main():
    audio_input = AudioInput()
    await audio_input.start()

if __name__ == "__main__":
    asyncio.run(main())