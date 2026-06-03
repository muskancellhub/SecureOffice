import { useNavigate } from 'react-router-dom';

export const BillingCancelledPage = () => {
  const navigate = useNavigate();

  return (
    <section className="content-wrap fade-in">
      <div className="content-head">
        <h1>Checkout Cancelled</h1>
      </div>

      <div className="table-wrap" style={{ padding: '2rem' }}>
        <p>Your checkout was cancelled. No charges were made.</p>
        <div style={{ marginTop: '1.5rem' }}>
          <button className="primary-btn" onClick={() => navigate(-1)}>
            Go Back
          </button>
        </div>
      </div>
    </section>
  );
};
