export const SupportPage = () => {
  return (
    <section className="content-wrap fade-in">
      <div className="content-head">
        <h1>Support</h1>
        <p className="lead">Need help setting up your router?</p>
      </div>

      <div className="chooser-grid">
        <article className="chooser-card disabled-card">
          <h3>Start chat</h3>
          <p>Live support chat (coming soon).</p>
        </article>
        <article className="chooser-card disabled-card">
          <h3>Start support call</h3>
          <p>Schedule a support engineer callback (coming soon).</p>
        </article>
        <article className="chooser-card disabled-card">
          <h3>FAQ / Knowledge base</h3>
          <p>Self-service docs and guides (coming soon).</p>
        </article>
      </div>
    </section>
  );
};
