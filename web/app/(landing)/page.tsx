import TumorFilm from "./TumorFilm";

export default function LandingPage() {
  return (
    <>
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="masthead">
      <div className="frame masthead-inner">
        <a className="wordmark" href="#main">Mini-Nota</a>
        <nav aria-label="On this page">
          <a href="#workflow">Workflow</a>
          <a href="#data">Data and findings</a>
          <a href="#technology">Technology</a>
        </nav>
        <a className="masthead-workspace" href="/workspace">Run an analysis</a>
      </div>
    </header>

    <main id="main" tabIndex={-1}>
      <section className="frame hero" aria-labelledby="hero-title">
        <div className="intro-copy">
          <h1 id="hero-title">From CT scans<br className="desktop-break" />{" "}to risk rankings.</h1>
          <p>Follow a public Lung1 cohort from scan checks to survival-risk rankings.</p>
          <div className="actions">
            <a className="btn btn-primary" href="#completed-run">View demo run</a>
            <a className="btn btn-secondary" href="/workspace">Run your own analysis</a>
          </div>
        </div>
        <figure className="scan">
          <div className="scan-heading"><span>Scan to measurements</span><span>LUNG1-002</span></div>
          <div className="scan-image">
            <TumorFilm />
          </div>
          <figcaption>111 CT slices. Tumor contours on 26 slices form the 3D mask.</figcaption>
        </figure>
      </section>
      <section className="section workflow-section" id="workflow" aria-labelledby="workflow-title">
        <div className="frame">
          <h2 id="workflow-title">The imaging workflow</h2>
          <ol className="workflow">
            <li><h3>Check scans</h3><p>Check DICOM metadata and scan geometry.</p></li>
            <li><h3>Build masks</h3><p>Convert tumor contours to aligned 3D masks.</p></li>
            <li><h3>Measure tumors</h3><p>Extract 72 shape, intensity, and texture features.</p></li>
            <li><h3>Rank risk</h3><p>Score eligible patients with a frozen Cox model.</p></li>
          </ol>
          <aside className="gate" aria-labelledby="gate-title">
            <h3 id="gate-title">Human gate</h3>
            <p>Flags, processing failures, or evaluation exclusions pause scoring for approval. Compute is released while the run waits.</p>
          </aside>
        </div>
      </section>

      <section className="section data-section" id="data" aria-labelledby="data-title">
        <div className="frame">
          <h2 id="data-title">Data and findings</h2>
          <div className="data-grid">
            <div className="cohort">
              <h3>The Lung1 cohort</h3>
              <p><a href="https://www.cancerimagingarchive.net/collection/nsclc-radiomics/">TCIA NSCLC-Radiomics</a> provides pretreatment CT, clinician-drawn tumor contours, and survival follow-up.</p>
              <dl className="cohort-counts">
                <div><dt>Source patients</dt><dd>422</dd></div>
                <div><dt>Usable after preparation</dt><dd>414</dd></div>
                <div><dt>Development cohort</dt><dd>332</dd></div>
                <div><dt>Held-out test cohort</dt><dd>82</dd></div>
              </dl>
            </div>
            <figure className="benchmark">
              <h3>Harrell’s C-index</h3>
              <p className="estimate">0.606</p>
              <figcaption>95% bootstrap interval, 0.533 to 0.674</figcaption>
              <div className="interval" aria-hidden="true">
                <div className="interval-axis"><span className="interval-range"></span><span className="interval-marker"></span></div>
                <div className="interval-labels"><span>0.50</span><span>0.60</span><span>0.70</span></div>
              </div>
              <p>Modest agreement between risk rankings and observed outcomes.</p>
            </figure>
          </div>
        </div>
      </section>

      <section className="section technology-section" id="technology" aria-labelledby="technology-title">
        <div className="frame">
          <h2 id="technology-title">Technology behind the run</h2>
          <dl className="stack">
            <div><dt>Scan checks and masks</dt><dd>pydicom for DICOM checks. RT-Utils and OpenCV for masks.</dd></div>
            <div><dt>Image measurements</dt><dd>SimpleITK for geometry. PyRadiomics for features.</dd></div>
            <div><dt>Survival analysis</dt><dd>scikit-learn for training. lifelines for Cox fitting and evaluation.</dd></div>
            <div><dt>App and patient catalog</dt><dd>Next.js, React, TypeScript, and GraphQL on Vercel. IndexedDB for History.</dd></div>
            <div><dt>Dispatch and compute</dt><dd>FastAPI on Render dispatches jobs. Modal runs imaging.</dd></div>
            <div><dt>Durable results</dt><dd>Neon Postgres for run records. Cloudflare R2 for scans and artifacts.</dd></div>
          </dl>
        </div>
      </section>

      <section className="section completed-section" id="completed-run" aria-labelledby="run-title">
        <div className="frame completed-grid">
          <div>
            <h2 id="run-title">The completed run</h2>
            <p>Explore scans, measurements, risk rankings, and the decision log for all 82 held-out patients.</p>
          </div>
          <div className="run-links">
            <a className="btn btn-primary" href="/workspace">Open Mini-Nota</a>
            <p>Choose <strong>View completed example</strong>.</p>
          </div>
        </div>
      </section>
    </main>
    <footer>
      <div className="frame footer-inner">
        <p><strong>Mini-Nota</strong><br />Independent research workflow demonstration. Not a medical device or medical advice.</p>
        <a href="https://github.com/kushp4444/mini-nota">GitHub</a>
      </div>
    </footer>
    </>
  );
}
