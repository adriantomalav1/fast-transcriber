import io
import json
import wave
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import Transcriber, create_app


def test_native_audio_decoder_compatibility():
    # Exercise the real PyAV/faster-whisper boundary without downloading a model.
    from faster_whisper.audio import decode_audio

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    buffer.seek(0)
    decoded = decode_audio(buffer)
    assert len(decoded) == 1600
    assert not decoded.any()


def test_real_worker_starts_and_stops_cleanly(tmp_path):
    service = Transcriber(tmp_path)
    service.start()
    try:
        assert service.process.is_alive()
    finally:
        service.stop()
    assert service.process.exitcode == 0


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Keep API tests deterministic and offline; drive the worker explicitly below.
    monkeypatch.setattr(Transcriber, "start", lambda self: None)
    monkeypatch.setattr(Transcriber, "stop", lambda self: None)
    monkeypatch.setattr(Transcriber, "submit", lambda self, job_id: None)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        yield client


def upload(client, name="interview.mp3", content=b"audio"):
    return client.post("/api/jobs", files={"file": (name, content, "audio/mpeg")})


@pytest.mark.parametrize("filename,content,code", [
    ("recording.wav", b"audio", 400),
    ("empty.mp3", b"", 400),
])
def test_reject_invalid_uploads(client, filename, content, code):
    response = upload(client, filename, content)
    assert response.status_code == code
    assert not list(client.app.state.transcriber.jobs_dir.iterdir())


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr("backend.main.MAX_UPLOAD_BYTES", 4)
    assert upload(client, content=b"12345").status_code == 413
    assert not list(client.app.state.transcriber.jobs_dir.iterdir())


def test_job_is_accepted_before_transcribing_and_download_waits(client):
    response = upload(client)
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "queued"
    assert client.get(f"/api/jobs/{job['id']}/download").status_code == 409
    assert client.get("/api/health").json()["status"] == "ok"


def test_full_long_transcript_and_utf8_download(client):
    service = client.app.state.transcriber
    # A late segment catches accidental truncation at 30 minutes or partial iteration.
    duration = 37 * 60 + 10

    class Model:
        def transcribe(self, path, **options):
            assert options["vad_filter"] is True
            assert options["beam_size"] == 5
            assert service.job_dir(job["id"]).joinpath("audio.mp3").read_bytes() == b"audio"

            def segments():
                yield SimpleNamespace(text=" First sentence. ", end=10)
                yield SimpleNamespace(text="Después de treinta minutos.", end=35 * 60)
                yield SimpleNamespace(text="The very end.", end=duration)

            return segments(), SimpleNamespace(duration=duration, language="es")

    service.model = Model()
    job = upload(client, "../café interview.MP3").json()
    service.transcribe(job["id"])
    status = client.get(f"/api/jobs/{job['id']}").json()
    assert status["status"] == "completed"
    assert status["progress"] == 100
    assert status["duration"] > 1800
    response = client.get(f"/api/jobs/{job['id']}/download")
    assert response.text == "First sentence.\nDespués de treinta minutos.\nThe very end.\n"
    assert response.headers["content-type"].startswith("text/plain")
    assert "caf%C3%A9%20interview.txt" in response.headers["content-disposition"]
    assert not (service.job_dir(job["id"]) / "audio.mp3").exists()
    assert not (service.job_dir(job["id"]) / "transcript.part").exists()


def test_model_failure_is_reported_and_audio_removed(client):
    class BrokenModel:
        def transcribe(self, *args, **kwargs):
            raise ValueError("Corrupt MP3")

    service = client.app.state.transcriber
    service.model = BrokenModel()
    job = upload(client).json()
    service.transcribe(job["id"])
    status = client.get(f"/api/jobs/{job['id']}").json()
    assert status["status"] == "failed"
    assert status["error"]
    assert not (service.job_dir(job["id"]) / "audio.mp3").exists()
    assert client.get(f"/api/jobs/{job['id']}/download").status_code == 409


def test_interrupted_jobs_fail_on_restart_but_completed_files_survive(client):
    service = client.app.state.transcriber
    pending = upload(client).json()
    completed = upload(client).json()
    directory = service.job_dir(completed["id"])
    (directory / "transcript.txt").write_text("Saved transcript.\n")
    service.write(completed["id"], status="completed", progress=100)
    (service.job_dir(pending["id"]) / "transcript.part").write_text("Unfinished")
    service.recover()
    assert service.read(pending["id"])["status"] == "failed"
    assert not (service.job_dir(pending["id"]) / "audio.mp3").exists()
    assert not (service.job_dir(pending["id"]) / "transcript.part").exists()
    assert client.get(f"/api/jobs/{completed['id']}/download").text == "Saved transcript.\n"


@pytest.mark.parametrize("job_id", ["not-a-uuid", str(uuid4()), "..%2F..%2Fetc"])
def test_unknown_or_unsafe_ids_return_404(client, job_id):
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_job_metadata_is_persisted(client):
    job = upload(client).json()
    metadata = client.app.state.transcriber.job_dir(job["id"]) / "job.json"
    assert json.loads(metadata.read_text())["filename"] == "interview.mp3"


def test_crashed_worker_is_reported_instead_of_polling_forever(client):
    job = upload(client).json()
    client.app.state.transcriber.process = SimpleNamespace(is_alive=lambda: False)
    response = client.get(f"/api/jobs/{job['id']}")
    assert response.json()["status"] == "failed"
    assert "worker stopped" in response.json()["error"]
    assert upload(client).status_code == 503
