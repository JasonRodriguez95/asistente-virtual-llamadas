from openai import OpenAI
import yaml
from pathlib import Path
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import PyPDF2
from docx import Document
import os
from datetime import datetime

class LLMProcessor:
    """Clase para procesar transcripciones usando la API de Grok (xAI) con historial conversacional, RAG y logging."""

    def __init__(self, config_path=None, prompt_path=None, documents_dir=None):
        """Inicializa el cliente de xAI, el historial, el sistema RAG y el logging."""
        # Rutas relativas al archivo llm_processor.py
        base_path = Path(__file__).parent  # Directorio src
        
        if config_path is None:
            config_path = base_path.parent / "config" / "config.yaml"
        if prompt_path is None:
            prompt_path = base_path.parent / "config" / "prompt.yaml"
        if documents_dir is None:
            documents_dir = base_path / "documents"

        # Cargar configuración de xAI
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["xai"]
        
        self.api_key = config["api_key"]
        self.model = config["model"]
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.x.ai/v1"
        )

        # Cargar el prompt desde un archivo externo
        with open(prompt_path, "r") as f:
            prompt_config = yaml.safe_load(f)
            self.system_prompt = prompt_config["system_prompt"]

        # Historial de la conversación
        self.conversation_history = [{"role": "system", "content": self.system_prompt}]

        # Configurar RAG
        self.documents = self._load_documents(documents_dir)
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.index, self.document_chunks = self._create_vector_store()

        # Configuración del archivo de log
        self.log_dir = base_path / "logs"  # src/logs
        self.log_dir.mkdir(exist_ok=True)
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"chat_{current_date}.txt"
        self._initialize_log()

    def _initialize_log(self):
        """Inicializa o reinicia el archivo de log según la fecha actual."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        new_log_file = self.log_dir / f"chat_{current_date}.txt"

        # Si el archivo actual no coincide con la fecha de hoy
        if new_log_file != self.log_file and self.log_file.exists():
            # Eliminar el archivo antiguo
            os.remove(self.log_file)
            print(f"🗑️ Archivo de log anterior {self.log_file} eliminado.")

        # Actualizar el archivo de log a usar
        self.log_file = new_log_file

        # Si el archivo no existe, crearlo e inicializarlo
        if not self.log_file.exists():
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write(f"Registro de conversación - {current_date}\n")
                f.write("=" * 50 + "\n")
            print(f"📝 Nuevo archivo de log creado: {self.log_file}")
        else:
            print(f"📝 Continuando con el archivo de log existente: {self.log_file}")

    def _log_message(self, role, content):
        """Registra un mensaje en el archivo de log con marca de tiempo."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {role.upper()}: {content}\n")

    def _load_documents(self, documents_dir):
        """Carga documentos desde una carpeta (PDF, Word, TXT)."""
        documents = []
        if not os.path.exists(documents_dir):
            print(f"⚠️ Carpeta {documents_dir} no encontrada. No se cargaron documentos para RAG.")
            return documents
        
        for filename in os.listdir(documents_dir):
            filepath = os.path.join(documents_dir, filename)
            if filename.endswith('.pdf'):
                with open(filepath, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text() or ""
                documents.append(text)
            elif filename.endswith('.docx'):
                doc = Document(filepath)
                text = ""
                for para in doc.paragraphs:
                    text += para.text + "\n"
                documents.append(text)
            elif filename.endswith('.txt'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
                documents.append(text)
        print(f"✅ Cargados {len(documents)} documentos desde {documents_dir}")
        return documents

    def _create_vector_store(self):
        """Crea un almacén de vectores FAISS con los documentos."""
        if not self.documents:
            print("⚠️ No hay documentos para crear el vector store. RAG estará desactivado.")
            return None, []

        document_chunks = []
        for doc in self.documents:
            for i in range(0, len(doc), 500):
                chunk = doc[i:i+500]
                document_chunks.append(chunk)

        embeddings = self.embedding_model.encode(document_chunks, convert_to_numpy=True)
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)

        print(f"✅ Vector store creado con {len(document_chunks)} fragmentos")
        return index, document_chunks

    def _retrieve_relevant_docs(self, query, top_k=3):
        """Recupera los documentos más relevantes para la consulta."""
        if self.index is None or not self.document_chunks:
            print("⚠️ No hay vector store disponible. Procesando sin RAG.")
            return []
        
        query_embedding = self.embedding_model.encode([query], convert_to_numpy=True)
        distances, indices = self.index.search(query_embedding, top_k)
        relevant_docs = [self.document_chunks[i] for i in indices[0]]
        print(f"🔍 Documentos relevantes recuperados: {len(relevant_docs)}")
        return relevant_docs

    def process(self, transcript):
        """Envía la transcripción a Grok con historial y documentos RAG, y devuelve la respuesta."""
        # Registrar la transcripción del usuario
        self._log_message("usuario", transcript)

        # Recuperar documentos relevantes
        relevant_docs = self._retrieve_relevant_docs(transcript)
        context = "\n".join(relevant_docs) if relevant_docs else "No hay contexto adicional disponible."
        
        # Crear prompt con contexto RAG
        rag_prompt = f"Contexto adicional:\n{context}\n\nTranscripción del usuario: {transcript}"
        self.conversation_history.append({"role": "user", "content": rag_prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                max_tokens=200,
                temperature=0.2
            )
            assistant_response = response.choices[0].message.content
            self.conversation_history.append({"role": "assistant", "content": assistant_response})
            # Registrar la respuesta de la IA
            self._log_message("eva", assistant_response)
            return assistant_response
        except Exception as e:
            error_msg = f"Error al procesar con Grok: {str(e)}"
            self.conversation_history.append({"role": "assistant", "content": error_msg})
            # Registrar el error
            self._log_message("eva", error_msg)
            return error_msg

    def reset_conversation(self):
        """Reinicia el historial de la conversación y verifica si hay que reiniciar el log."""
        self.conversation_history = [{"role": "system", "content": self.system_prompt}]
        current_date = datetime.now().strftime("%Y-%m-%d")
        new_log_file = self.log_dir / f"chat_{current_date}.txt"
        if new_log_file != self.log_file:
            self.log_file = new_log_file
            self._initialize_log()
