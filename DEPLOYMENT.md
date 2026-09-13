# Deploy gratuito para la demo

La configuración recomendada es **Vercel para `frontend`** y **Render para la API FastAPI**. La aplicación usa WebSockets para los cambios en tiempo real de la simulación; Render los admite en su servicio web. No se necesita Supabase mientras las simulaciones sean temporales, como ahora.

## 1. Sube el repositorio a GitHub

No publiques los archivos `.env.*.local`. Ya están excluidos por `.gitignore`.

## 2. API en Render

1. En [Render](https://render.com), crea **New > Blueprint** e importa el repositorio.
2. Render detectará `render.yaml`. Confirma el servicio `courier-api` en el plan **Free**.
3. En las variables de entorno, agrega `CORS_ORIGINS` con la URL de producción de Vercel, por ejemplo `https://courier-demo.vercel.app`. Para probar antes de tener esa URL, usa temporalmente `*`.
4. Si se mostrarán explicaciones o voz reales, agrega también `GEMINI_ENABLED=true`, `GEMINI_API_KEY` y/o `ELEVENLABS_API_KEY`. Si no, la demo funciona con los fallbacks y sin exponer claves.
5. Al terminar, copia la URL de Render, por ejemplo `https://courier-api.onrender.com`, y comprueba `https://courier-api.onrender.com/healthz`.

## 3. Frontend en Vercel

1. En [Vercel](https://vercel.com), importa el mismo repositorio. El archivo `vercel.json` ya indica cómo compilar el subdirectorio `frontend`.
2. En **Settings > Environment Variables**, crea `VITE_API_URL` con la URL HTTPS de Render, sin `/` final.
3. Haz el deploy. Copia su URL y úsala como valor de `CORS_ORIGINS` en Render; después redeploya Render.

## 4. Ensayo de entrega

Abre la URL de Vercel, inicia una simulación y verifica que el indicador de conexión quede activo. La primera llamada tras 15 minutos sin uso puede tardar alrededor de un minuto: abre `/healthz` de Render uno o dos minutos antes de presentar para despertar el servicio.

## Nota sobre datos

El estado de las simulaciones vive en memoria. Un redeploy, reinicio o suspensión de Render lo borra; esto no afecta una demo recién iniciada. Si necesitan historial compartido o persistente, entonces añadan Supabase Postgres, pero no es necesario para este despliegue.
