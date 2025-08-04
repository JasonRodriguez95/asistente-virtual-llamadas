import sys

def display_transcriptions():
    print("🎙️ Terminal de transcripciones iniciada. Escuchando...")
    while True:
        # Leer desde stdin (pipe)
        transcript = sys.stdin.readline().strip()
        if not transcript or transcript == "EXIT":
            break
        print(f"Transcripción recibida: {transcript}")
    print("📌 Terminal de transcripciones cerrada.")

if __name__ == "__main__":
    display_transcriptions()