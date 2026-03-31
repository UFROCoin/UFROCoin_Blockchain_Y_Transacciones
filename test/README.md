# UFROCoin - Prueba de Concepto (PoC)

Esta es la implementación de referencia para el stack tecnológico validado para el proyecto UFROCoin.

## Stack Tecnológico

- **Base de Datos:** MongoDB v8.0 (Docker)
- **Backend:** Python + FastAPI (v0.135.2)
- **Frontend:** Vue.js (v3.5.x) + Vite (v6.0.x)

## Prerrequisitos

- Docker y Docker Compose instalados en el sistema.
- Python 3.10 o superior.
- Node.js 20.x o superior.

## Instrucciones de Ejecución

Para iniciar el proyecto correctamente, es necesario abrir tres terminales distintas en la raíz del proyecto para mantener los procesos de desarrollo en ejecución simultánea.

### 1. Levantar la Base de Datos (Terminal 1)

Desde la raíz del proyecto, inicializa el contenedor de MongoDB en segundo plano:

```bash
docker compose up -d
```

### 2. Levantar el Backend (Terminal 2)

Navega al directorio del backend, configura el entorno virtual, instala las dependencias y ejecuta el servidor de la API:

```bash
cd backend
python -m venv venv

# En Windows:
.\venv\Scripts\activate
# En macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

La API REST y su documentación Swagger UI estarán disponibles en: `http://localhost:8000/docs`

### 3. Levantar el Frontend (Terminal 3)

Navega al directorio del frontend, instala los paquetes de Node y levanta el servidor de desarrollo de Vite:

```bash
cd frontend
npm install
npm run dev
```

La aplicación web estará disponible y lista para pruebas en: `http://localhost:5173/`