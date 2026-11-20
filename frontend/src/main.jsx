import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const STORAGE_KEY = 'fast-transcriber:last-job';
const MAX_BYTES = 2 * 1024 ** 3;

function remember(id) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id);
    else localStorage.removeItem(STORAGE_KEY);
  } catch { /* Transcription still works with browser storage disabled. */ }
}

function previousJob() {
  try { return localStorage.getItem(STORAGE_KEY); }
  catch { return null; }
}

function Icon({ name, ...props }) {
  const paths = {
    upload: <><path d="M12 16V4m-4 4 4-4 4 4" /><path d="M4 16v4h16v-4" /></>,
    file: <><path d="M14 3H5v18h14V8l-5-5Z" /><path d="M14 3v5h5M8 13h8m-8 4h6" /></>,
    download: <><path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>;
}

function durationLabel(seconds) {
  if (!seconds) return '';
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m ${Math.floor(seconds % 60)}s`;
}

async function responseError(response) {
  try { return (await response.json()).detail || 'Something went wrong. Please try again.'; }
  catch { return 'Something went wrong. Please try again.'; }
}

function App() {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState(previousJob);
  const [job, setJob] = useState(null);
  const [error, setError] = useState('');
  const [connectionError, setConnectionError] = useState('');
  const [transcript, setTranscript] = useState(null);
  const [previewError, setPreviewError] = useState('');
  const input = useRef(null);
  const terminal = job?.status === 'completed' || job?.status === 'failed';
  const busy = uploading || Boolean(jobId && !terminal);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer;
    const controller = new AbortController();

    async function poll() {
      try {
        const response = await fetch(`/api/jobs/${jobId}`, { signal: controller.signal });
        if (cancelled) return;
        if (response.status === 404) {
          remember(null);
          setJobId(null);
          setError('The previous transcription is no longer available. Please upload your MP3 again.');
          return;
        }
        if (!response.ok) throw new Error('Status unavailable');
        const next = await response.json();
        if (cancelled) return;
        setJob(next);
        setConnectionError('');
        if (next.status === 'completed' || next.status === 'failed') return;
      } catch {
        if (cancelled) return;
        setConnectionError('Reconnecting to the local server. Keep npm start running; this page will retry automatically.');
      }
      timer = setTimeout(poll, 1500);
    }
    poll();
    return () => { cancelled = true; clearTimeout(timer); controller.abort(); };
  }, [jobId]);

  useEffect(() => {
    if (job?.status !== 'completed') return;
    const controller = new AbortController();
    async function preview() {
      try {
        const response = await fetch(`/api/jobs/${job.id}/download`, { signal: controller.signal });
        if (!response.ok) throw new Error('Preview unavailable');
        const text = await response.text();
        if (!controller.signal.aborted) setTranscript(text);
      } catch {
        if (!controller.signal.aborted) setPreviewError('Preview unavailable. You can still download your transcript.');
      }
    }
    preview();
    return () => controller.abort();
  }, [job?.id, job?.status]);

  function chooseFile(next) {
    if (busy) return;
    setError('');
    if (!next) return;
    if (!next.name.toLowerCase().endsWith('.mp3')) {
      setFile(null);
      setError('Please choose an MP3 file.');
      return;
    }
    if (!next.size || next.size > MAX_BYTES) {
      setFile(null);
      setError(next.size ? 'The MP3 must be smaller than 2 GB.' : 'This file is empty. Please choose a playable MP3.');
      return;
    }
    setFile(next);
    if (input.current) input.current.value = '';
  }

  async function transcribe(event) {
    event.preventDefault();
    if (!file || busy) return;
    setUploading(true);
    setError('');
    setJob(null);
    setTranscript(null);
    setPreviewError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await fetch('/api/jobs', { method: 'POST', body: form });
      if (!response.ok) throw new Error(await responseError(response));
      const created = await response.json();
      remember(created.id);
      setJob(created);
      setJobId(created.id);
    } catch (failure) {
      setError(failure instanceof TypeError ? 'Cannot reach the local server. Make sure npm start is running, then try again.' : failure.message);
    } finally { setUploading(false); }
  }

  function reset() {
    remember(null);
    setJobId(null);
    setJob(null);
    setFile(null);
    setTranscript(null);
    setError('');
    setPreviewError('');
    setConnectionError('');
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a href="/" className="wordmark" aria-label="Fast Transcriber home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /><i /><i /></span>
          Fast Transcriber
        </a>
        <span className="local-badge"><Icon name="lock" />Local & private</span>
      </header>

      <main>
        <div className="intro">
          <p className="eyebrow">LESS LISTENING. MORE DOING.</p>
          <h1>Your audio,<br /><span>in plain text.</span></h1>
          <p className="intro-copy">Drop in an MP3. Get a transcript.<br className="mobile-break" /> All on your own computer.</p>
        </div>

        {!jobId && !uploading ? (
          <form className="workspace" onSubmit={transcribe}>
            <div className="card-heading"><h2>Start a transcription</h2><span>MP3 → TXT</span></div>
            <label className={`dropzone ${dragging ? 'dragging' : ''}`} htmlFor="audio-file"
              onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files[0]); }}>
              <input ref={input} id="audio-file" className="file-input" type="file" accept=".mp3,audio/mpeg" onChange={(event) => chooseFile(event.target.files[0])} />
              <span className="upload-icon"><Icon name="upload" /></span>
              <strong>{file ? 'Your audio is ready' : 'Drop your MP3 here'}</strong>
              <span className="dropzone-copy">or <span className="text-link">{file ? 'choose a different file' : 'browse files'}</span></span>
              <span className="file-limit">Up to 2 GB · Recordings over 30 minutes welcome</span>
            </label>

            {file && <div className="selected-file"><span className="file-icon"><Icon name="file" /></span><div><strong>{file.name}</strong><span>{(file.size / 1024 ** 2).toFixed(1)} MB</span></div><button type="button" className="icon-button" onClick={() => setFile(null)} aria-label="Remove selected file"><Icon name="close" /></button></div>}
            {error && <p className="message error" role="alert">{error}</p>}
            <button className="primary-button" type="submit" disabled={!file}>Transcribe audio</button>
            <p className="card-note">Language detected automatically. Download as a .txt file.</p>
          </form>
        ) : job?.status === 'completed' ? (
          <section className="workspace" aria-labelledby="complete-title">
            <div className="result-heading"><span className="success-icon"><Icon name="check" /></span><div><p className="eyebrow">ALL DONE</p><h2 id="complete-title">Your transcript is ready.</h2></div></div>
            <p className="result-filename">{job.filename}</p>
            <div className="metadata"><span>{durationLabel(job.duration)} of audio</span><span>Language: {job.language?.toUpperCase()}</span><span>Plain text · UTF-8</span></div>
            {transcript !== null ? <div className="transcript-preview" tabIndex={0} aria-label="Transcript preview">{transcript.trim() ? transcript.slice(0, 8000) : 'No speech was detected in this recording.'}{transcript.length > 8000 && '\n\n… Download the .txt file for the full transcript.'}</div> : <p className="card-note">{previewError || 'Loading preview…'}</p>}
            <a className="primary-button" href={`/api/jobs/${job.id}/download`} download><Icon name="download" />Download transcript</a>
            <button className="secondary-button" onClick={reset}>Transcribe another file</button>
          </section>
        ) : job?.status === 'failed' ? (
          <section className="workspace" aria-labelledby="failed-title">
            <h2 id="failed-title">We couldn’t finish this transcription.</h2>
            <p className="message error" role="alert">{job.error}</p>
            <button className="primary-button" onClick={reset}>Choose an MP3 again</button>
          </section>
        ) : (
          <section className="workspace processing" aria-labelledby="progress-title" aria-busy="true">
            <div className="processing-icon" aria-hidden="true"><span className="spinner" /></div>
            <h2 id="progress-title">{uploading ? 'Uploading your audio…' : job?.stage || 'Finding your transcription…'}</h2>
            <p className="processing-filename">{job?.filename || file?.name}</p>
            {job?.stage === 'Transcribing' ? <><div className="progress-label"><span>Audio processed</span><span>{job.progress}%</span></div><progress max="100" value={job.progress} aria-label="Audio processed" /></> : <progress aria-label={uploading ? 'Uploading audio' : 'Preparing transcription'} />}
            <p className="processing-note">{uploading ? 'Sending the file to your local server.' : job?.stage === 'Loading speech model' ? 'First use downloads the speech model. This can take a few minutes.' : job?.status === 'queued' ? 'Waiting for the transcription worker.' : 'Long recordings can take a while. You can refresh this page and come back.'}</p>
            {connectionError && <p className="message" role="status">{connectionError}</p>}
          </section>
        )}

        <div className="reassurance"><Icon name="lock" /><p>Your audio stays on this computer.<br /><span>Powered by faster-whisper. No account or API key needed.</span></p></div>
      </main>
      <footer>Made for the moments worth keeping.</footer>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
