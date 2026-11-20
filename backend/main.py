"""One local server, one transcription worker, and files on disk."""

import json
import logging
import multiprocessing
import os
import signal
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".data"
MAX_UPLOAD_BYTES = 2 * 1024**3
logger = logging.getLogger("uvicorn.error")


class Transcriber:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.jobs_dir = data_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = os.environ.get("WHISPER_MODEL", "small")
        self.model = None
        self.lock = Lock()
        self.process = None
        self.queue = None

    def start(self):
        # A separate process keeps the API responsive and can stop promptly on Ctrl+C.
        context = multiprocessing.get_context("spawn")
        self.queue = context.Queue()
        self.process = context.Process(target=run_worker, args=(self.data_dir, self.queue), daemon=True)
        self.process.start()

    def stop(self):
        if self.process is not None:
            # Let an idle worker exit cleanly; interrupt active inference promptly.
            self.queue.put(None)
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=5)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join()
        if self.queue is not None:
            self.queue.cancel_join_thread()
            self.queue.close()

    def job_dir(self, job_id: str) -> Path:
        try:
            # Accept only canonical UUIDs; never use user filenames as paths.
            if str(UUID(job_id)) != job_id:
                raise ValueError
        except ValueError:
            raise HTTPException(404, "Transcription not found.") from None
        return self.jobs_dir / job_id

    def read(self, job_id: str) -> dict:
        with self.lock:
            try:
                return json.loads((self.job_dir(job_id) / "job.json").read_text())
            except FileNotFoundError:
                raise HTTPException(404, "Transcription not found.") from None

    def write(self, job_id: str, **changes) -> dict:
        with self.lock:
            directory = self.job_dir(job_id)
            metadata = directory / "job.json"
            job = json.loads(metadata.read_text()) if metadata.exists() else {}
            job.update(changes)
            # Atomic replace prevents polling from reading half-written JSON.
            temporary = directory / "job.json.tmp"
            temporary.write_text(json.dumps(job), encoding="utf-8")
            temporary.replace(metadata)
            return job

    def recover(self):
        for metadata in self.jobs_dir.glob("*/job.json"):
            job = self.read(metadata.parent.name)
            if job["status"] in {"queued", "processing"}:
                self.write(job["id"], status="failed", stage="Interrupted",
                           error="The server stopped before this finished. Please upload the MP3 again.")
            (metadata.parent / "audio.mp3").unlink(missing_ok=True)
            (metadata.parent / "transcript.part").unlink(missing_ok=True)

    def submit(self, job_id: str):
        self.queue.put(job_id)

    def transcribe(self, job_id: str):
        directory = self.job_dir(job_id)
        partial = directory / "transcript.part"
        try:
            self.write(job_id, status="processing", stage="Loading speech model")
            if self.model is None:
                # Lazy import: the UI starts immediately; download happens on first use.
                from faster_whisper import WhisperModel

                self.model = WhisperModel(
                    self.model_name, device="cpu", compute_type="int8",
                    cpu_threads=max(1, min(8, os.cpu_count() or 1)),
                    download_root=str(self.data_dir / "models"),
                )
            self.write(job_id, stage="Reading audio")
            segments, info = self.model.transcribe(
                str(directory / "audio.mp3"), beam_size=5, vad_filter=True,
            )
            self.write(job_id, stage="Transcribing", duration=info.duration,
                       language=info.language)
            # Consume the ENTIRE generator: no 30-minute cut-off or request timeout.
            # Write incrementally rather than collecting the transcript in memory.
            with partial.open("w", encoding="utf-8") as transcript:
                for segment in segments:
                    line = segment.text.strip()
                    if line:
                        transcript.write(line + "\n")
                    progress = min(99, int(segment.end / max(info.duration, 0.001) * 100))
                    self.write(job_id, progress=progress)
            partial.replace(directory / "transcript.txt")
            self.write(job_id, status="completed", stage="Ready", progress=100)
        except Exception:
            logger.exception("Transcription failed for %s", job_id)
            partial.unlink(missing_ok=True)
            self.write(job_id, status="failed", stage="Could not transcribe",
                       error="Could not transcribe this file. Check that it is a playable MP3, "
                             "that there is enough free memory and disk space, and that the "
                             "first model download has internet access. See the terminal for details.")
        finally:
            (directory / "audio.mp3").unlink(missing_ok=True)


def run_worker(data_dir: Path, queue):
    # The parent handles Ctrl+C and terminates this worker during shutdown.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    service = Transcriber(data_dir)
    while True:
        job_id = queue.get()
        if job_id is None:
            return
        service.transcribe(job_id)


def create_app(data_dir: Path = DATA) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = Transcriber(data_dir)
        service.recover()
        service.start()
        app.state.transcriber = service
        try:
            yield
        finally:
            service.stop()

    app = FastAPI(title="Fast Transcriber", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "model": app.state.transcriber.model_name}

    @app.post("/api/jobs", status_code=202)
    def upload(file: UploadFile):
        service = app.state.transcriber
        directory = None
        try:
            if service.process is not None and not service.process.is_alive():
                raise HTTPException(503, "The transcription worker stopped. Please restart npm start.")
            filename = (file.filename or "").replace("\\", "/").split("/")[-1]
            if not filename.lower().endswith(".mp3"):
                raise HTTPException(400, "Please choose an MP3 file.")
            if file.size is not None and file.size > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "The MP3 must be smaller than 2 GB.")
            job_id = str(uuid4())
            directory = service.job_dir(job_id)
            directory.mkdir()
            size = 0
            with (directory / "audio.mp3").open("wb") as audio:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "The MP3 must be smaller than 2 GB.")
                    audio.write(chunk)
            if size == 0:
                raise HTTPException(400, "This file is empty. Please choose a playable MP3.")
            job = service.write(
                job_id, id=job_id, filename=filename, status="queued", stage="Queued",
                progress=0, duration=None, language=None, error=None,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            service.submit(job_id)
            return job
        except Exception:
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            file.file.close()

    @app.get("/api/jobs/{job_id}")
    def status(job_id: str):
        service = app.state.transcriber
        job = service.read(job_id)
        if job["status"] in {"queued", "processing"} and service.process is not None and not service.process.is_alive():
            job = service.write(job_id, status="failed", stage="Worker stopped",
                                error="The transcription worker stopped. This can happen if memory runs out. "
                                      "Restart npm start, then try a smaller model or recording.")
        return job

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str):
        service = app.state.transcriber
        job = service.read(job_id)
        if job["status"] != "completed":
            raise HTTPException(409, "The transcript is not ready yet.")
        return FileResponse(
            service.job_dir(job_id) / "transcript.txt",
            media_type="text/plain; charset=utf-8",
            filename=Path(job["filename"]).stem + ".txt",
        )

    # Register API routes first so missing API URLs remain genuine 404s.
    frontend = ROOT / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
