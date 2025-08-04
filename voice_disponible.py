from elevenlabs import ElevenLabs

# Configura tu clave API directamente en el código
api_key = "sk_f6c8c557b8c0397cb1ea96f5ea0bbd27b3a6d5087a8701c7"

# Crear una instancia del cliente de ElevenLabs
client = ElevenLabs(api_key=api_key)

# Función para listar las voces disponibles
def listar_voces():
    print("Obteniendo lista de voces disponibles...")
    # Obtener todas las voces
    voices = client.voices.get_all()
    print("Voces disponibles (estructura cruda):")
    print(voices)  # Imprimimos la respuesta completa para inspeccionarla
    
    # Iterar sobre las voces y mostrar nombre e ID
    print("Voces disponibles:")
    for voice in voices.voices:  # Accedemos al atributo 'voices' que contiene la lista
        print(f"Nombre: {voice.name}, ID: {voice.voice_id}")

# Llamar a la función para listar las voces
listar_voces()