'use strict';
(() => {
  let token = '', config = {};
  const el = id => document.getElementById(id);
  const message = text => { el('message').textContent = text; };
  async function api(path, body) {
    const headers = {};
    if (token) headers.Authorization = 'Bearer ' + token;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'omit', cache: 'no-store', redirect: 'error'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Request failed');
    return result;
  }
  async function status() {
    const who = await api('/api/me');
    el('identity').textContent = who.email;
    el('subscription').textContent = who.test_subscription_active ? 'Test subscription active. Live monitoring is still unavailable.' : 'No active test subscription. The free calculator is available.';
    el('checkout').disabled = !config.test_checkout_enabled || who.test_subscription_active;
    el('portal').disabled = !config.test_checkout_enabled;
    el('signin').hidden = true; el('signedin').hidden = false;
  }
  el('send-form').addEventListener('submit', async event => {
    event.preventDefault(); el('send').disabled = true;
    try { const result = await api('/api/auth/code', {email: el('email').value}); message(result.message); el('verify-form').hidden = false; }
    catch (error) { message(error.message); }
    finally { el('send').disabled = false; }
  });
  el('verify-form').addEventListener('submit', async event => {
    event.preventDefault();
    try { const result = await api('/api/auth/verify', {email: el('email').value, code: el('code').value}); token = result.access_token; el('code').value = ''; await status(); message('Signed in. Live payments are disabled.'); }
    catch (error) { token = ''; message(error.message); }
  });
  for (const [id, path, hostname] of [['checkout', '/api/checkout', 'checkout.stripe.com'], ['portal', '/api/portal', 'billing.stripe.com']]) {
    el(id).addEventListener('click', async () => {
      el(id).disabled = true;
      try { const result = await api(path, {}); const url = new URL(result.url); if (result.mode !== 'test' || url.protocol !== 'https:' || url.hostname !== hostname) throw new Error('Invalid test checkout destination'); window.location.assign(url.href); }
      catch (error) { message(error.message); el(id).disabled = false; }
    });
  }
  el('refresh').addEventListener('click', () => status().then(() => message('Status checked.')).catch(error => message(error.message)));
  el('logout').addEventListener('click', async () => {
    let failed = false;
    try { await api('/api/auth/logout', {}); } catch (_) { failed = true; }
    token = ''; el('signedin').hidden = true; el('signin').hidden = false;
    message(failed ? 'Local sign-in cleared. Server sign-out could not be confirmed; the short-lived token will expire.' : 'Signed out.');
  });
  api('/api/config').then(result => { config = result; el('signin').hidden = !result.accounts_enabled; message(result.accounts_enabled ? 'Sign in with a code or copied confirmation link sent to your email. Live charges are disabled.' : 'Customer accounts are being prepared. Sign-in and test checkout are unavailable until configuration is complete.'); }).catch(() => message('Account service unavailable. Please try later.'));
})();
