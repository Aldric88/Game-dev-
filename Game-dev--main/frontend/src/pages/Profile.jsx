import { useEffect, useState } from 'react';
import { users } from '../api';
import './Profile.css';

export default function Profile() {
  const [profile, setProfile] = useState(null);
  const [usage, setUsage] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [loadingUsage, setLoadingUsage] = useState(true);
  const [username, setUsername] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    users.getProfile()
      .then((data) => {
        setProfile(data);
        setUsername(data.username || '');
      })
      .catch(() => {})
      .finally(() => setLoadingProfile(false));

    users.getUsage()
      .then(setUsage)
      .catch(() => {})
      .finally(() => setLoadingUsage(false));
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    const trimmed = username.trim();
    if (!trimmed || trimmed === profile?.username) return;
    setSaving(true);
    setSaveError('');
    setSaveSuccess(false);
    try {
      const updated = await users.updateProfile({ username: trimmed });
      setProfile(updated);
      setUsername(updated.username || trimmed);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const planLabel = profile?.plan
    ? profile.plan.charAt(0).toUpperCase() + profile.plan.slice(1)
    : 'Free';

  const creditsUsed = usage?.credits_used ?? 0;
  const creditsLimit = usage?.credits_limit ?? 0;
  const creditsRemaining = usage?.credits_remaining ?? (profile?.credits_remaining ?? 0);
  const apiCallsUsed = usage?.api_calls_used ?? profile?.api_calls ?? 0;
  const usagePct = creditsLimit > 0 ? Math.min((creditsUsed / creditsLimit) * 100, 100) : 0;

  return (
    <div className="profile-page">
      <div className="profile-container">
        <h1 className="profile-heading">Profile &amp; Settings</h1>
        <p className="profile-subheading">Manage your account details and view usage</p>

        {loadingProfile ? (
          <div className="profile-loading">
            <div className="profile-spinner" />
          </div>
        ) : (
          <>
            {/* ── Account Info ── */}
            <section className="profile-section">
              <h2 className="profile-section-title">Account</h2>
              <div className="profile-field-row">
                <span className="profile-label">Plan</span>
                <span className={`profile-plan-badge profile-plan-${profile?.plan || 'free'}`}>
                  {planLabel}
                </span>
              </div>
              <div className="profile-field-row">
                <span className="profile-label">Email</span>
                <span className="profile-value-readonly">{profile?.email || '—'}</span>
              </div>
              <div className="profile-field-row">
                <span className="profile-label">Credits Remaining</span>
                <span className="profile-value-mono">{creditsRemaining}</span>
              </div>
              <div className="profile-field-row">
                <span className="profile-label">API Calls Used</span>
                <span className="profile-value-mono">{apiCallsUsed}</span>
              </div>
            </section>

            {/* ── Edit Username ── */}
            <section className="profile-section">
              <h2 className="profile-section-title">Edit Profile</h2>
              <form className="profile-form" onSubmit={handleSave}>
                <label className="profile-input-label">Username</label>
                <div className="profile-input-row">
                  <input
                    className="profile-input"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Your username"
                    disabled={saving}
                    maxLength={64}
                  />
                  <button
                    type="submit"
                    className="profile-save-btn"
                    disabled={saving || !username.trim() || username.trim() === profile?.username}
                  >
                    {saving ? <div className="profile-spinner-sm" /> : 'Save'}
                  </button>
                </div>
                {saveError && <p className="profile-form-error">{saveError}</p>}
                {saveSuccess && <p className="profile-form-success">Username updated successfully.</p>}
              </form>
            </section>

            {/* ── Usage ── */}
            <section className="profile-section">
              <h2 className="profile-section-title">Usage</h2>
              {loadingUsage ? (
                <div className="profile-loading-inline">
                  <div className="profile-spinner-sm" />
                </div>
              ) : (
                <div className="profile-usage">
                  <div className="profile-usage-header">
                    <span className="profile-usage-label">Credits used this month</span>
                    <span className="profile-usage-numbers">
                      {creditsUsed} / {creditsLimit > 0 ? creditsLimit : '—'}
                    </span>
                  </div>
                  <div className="profile-usage-bar-track">
                    <div
                      className="profile-usage-bar-fill"
                      style={{ width: `${usagePct}%` }}
                    />
                  </div>
                  {creditsLimit > 0 && (
                    <p className="profile-usage-note">
                      {Math.round(usagePct)}% of monthly limit used
                    </p>
                  )}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
