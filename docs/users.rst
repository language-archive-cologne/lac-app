 .. _users:

Users
======================================================================

Starting a new project, it’s highly recommended to set up a custom user model,
even if the default User model is sufficient for you.

This model behaves identically to the default user model,
but you’ll be able to customize it in the future if the need arises.

Shibboleth / SAML login
----------------------------------------------------------------------

``lacos`` exposes Shibboleth single sign-on next to the existing Django
credentials page. When ``SAML_LOGIN_ENABLED`` is true, the login form renders a
"Sign in with university account" button that proxies to ``/saml2/login/``.
Successful assertions populate the local ``username`` from
``eduPersonPrincipalName`` and derive an ``acl_agent_uri`` from it for ACL
matching.

Key settings

* ``SAML_SP_BASE_URL`` – external HTTPS endpoint used to mint ACS and logout
  URLs.
* ``SAML_DJANGO_USER_MAIN_ATTRIBUTE`` – defaults to ``username`` so users are
  looked up by ``eduPersonPrincipalName`` (ePPN).
* ``SAML_IDP_METADATA_LOCAL`` / ``SAML_IDP_METADATA_REMOTE`` – IdP metadata
  sources. The repository ships a local fallback
  ``shibboleth.xml`` for development.
* The SP metadata advertises REFEDS Code of Conduct v2, REFEDS Research and
  Scholarship, and CLARIN member entity categories, matching LACOS' role as the
  KA3 successor service.

Operations runbook
----------------------------------------------------------------------

Metadata refresh
    Replace the local metadata file referenced in
    ``SAML_IDP_METADATA_LOCAL`` or update the remote URLs, then reload the
    ``django`` service. The SAML loader caches responses, so bump
    ``SAML_METADATA_CACHE_DURATION`` (default 24h) if the IdP rotates metadata
    faster.

Certificate rotation
    Mount new key/cert pairs at the paths supplied via ``SAML_SP_KEY_FILE`` and
    ``SAML_SP_CERT_FILE``. The docker compose files expect these paths to point
    at bind-mounted secrets (e.g. ``./secrets/saml`` in local test runs). Issue
    a rolling restart after replacing the files so xmlsec picks up the new
    material.

Troubleshooting
    ``HTTP 403``
        The IdP denied the request or attribute mapping rejected the payload.
        Confirm the IdP releases ``eduPersonPrincipalName`` and that the
        service is authorised for the selected scope.

    Attribute mismatch
        Inspect ``session_info['ava']`` in the Django shell while reproducing
        the login. Missing ``eduPersonPrincipalName`` values prevent account
        provisioning because the ePPN drives lookups.

    Redirect loops
        Ensure Traefik forwards ``X-Forwarded-Proto=https`` and that
        ``SAML_SP_BASE_URL`` matches the external host; a mismatch forces the
        SP to initiate a new login on every callback.

.. automodule:: lacos.users.models
   :members:
   :noindex:
