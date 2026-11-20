# Fast Transcriber

A small local app: upload an MP3, transcribe it with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), and download a UTF-8 `.txt` file. React frontend, FastAPI backend, no account or API key.

## Run

Prerequisites: **Node.js 22.12+** (with npm) and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**. You do not need to install Python, FFmpeg, Docker, or a database separately.

From this repository, run:

```sh
npm start
```

Open **http://127.0.0.1:8000**. Choose or drop an MP3, click **Transcribe audio**, then **Download transcript**. Stop the app with **Ctrl+C**.

The command installs Python 3.12 and locked dependencies when needed, builds the React app, and starts one local server. The first transcription downloads the multilingual `small` model (roughly 500 MB); allow a few minutes and keep the terminal running. Subsequent transcriptions reuse the model. Internet is needed for initial installation and uncached model downloads; transcription itself runs on your computer.

## Long recordings

There is **no application duration cutoff**: recordings longer than 30 minutes are supported, with a **2 GB upload limit**. Uploads are copied in chunks to disk. One background process handles recordings sequentially; the browser polls status instead of keeping a transcription request open. You can refresh or reopen the same browser and recover the latest job. Progress measures the audio position reached, not estimated time remaining.

Available RAM, disk space, and CPU speed still matter. faster-whisper decodes the recording into memory, so very long audio requires more RAM. CPU transcription can take a while. Language is detected automatically; text stays in the original language. Transcripts contain plain text without timestamps or speaker labels.

Finished transcripts survive server restarts. Stopping the server interrupts active and queued jobs; after restarting, upload those recordings again. Uploaded MP3 copies are deleted after success, failure, or restart recovery. Your original MP3 is untouched.

## Options

The default is CPU inference with INT8, including on Apple Silicon. To favor speed over accuracy, use `tiny` or `base`; to improve accuracy at a higher memory and time cost, use a larger multilingual model:

```sh
WHISPER_MODEL=base npm start
```

Change the port if 8000 is in use:

```sh
PORT=8001 npm start
```

## Everything stays in this repo

```text
frontend/       React source, Vite config, and npm lockfile
backend/        FastAPI, transcription worker, and API tests
scripts/        Single-command startup and test helpers
uv.lock         Locked Python dependencies
AGENTS.md       Instructions for future coding agents
.venv/          Local Python environment (ignored)
.python/        uv-managed Python installation (ignored)
.cache/         Package caches (ignored)
.data/models/   Downloaded speech models (ignored)
.data/jobs/     Job metadata and completed transcripts (ignored)
.data/tmp/      Temporary upload files (ignored)
```

`frontend/node_modules/` and `frontend/dist/` are also local and ignored. The app binds to `127.0.0.1` for use on this computer. It does not send audio to a transcription service. The browser stores only the latest job ID. To remove all saved transcripts, stop the app and delete `.data/jobs/`; to reclaim model disk space, delete `.data/models/` as well. Do not commit recordings, transcripts, caches, or environments.

## Development and checks

```sh
npm test        # Offline API/worker tests, after dependencies are installed
npm run build   # Frontend production build, after npm start has installed it
```

Tests cover native audio decoder compatibility, upload validation, background job acceptance, UTF-8 downloads, full consumption of a simulated recording over 30 minutes, worker failures, and restart recovery. They do not download a model.

For frontend hot reload, leave `npm start` running and in a second terminal run `npm --prefix frontend run dev`. Vite serves http://127.0.0.1:5173 and proxies `/api` to port 8000. Regular use only needs `npm start`.
